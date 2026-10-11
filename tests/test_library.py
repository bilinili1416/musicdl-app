import io
import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import wave
from pathlib import Path
from unittest.mock import patch

import librarytools
import lyrics
import server


def wav_bytes(seconds=2):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b'\0\0' * 8000 * seconds)
    return stream.getvalue()


class ImmediatePool:
    def submit(self, fn, *args):
        fn(*args)


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name) / 'state'
        self.output = Path(self.temp.name) / 'outputs'
        self.output.mkdir()
        self.patches = [patch.object(server, 'OUTPUT', self.output), patch.object(server, 'STATE', self.state),
                        patch.object(server, 'IMPORTS', {}), patch.object(server, 'JOBS', {}),
                        patch.object(server, 'IMPORT_POOL', ImmediatePool()), patch.object(server, 'AUTH_PASSWORD', ''),
                        patch.object(server, 'PUBLIC_ORIGIN', ''), patch.object(lyrics, 'candidates', return_value=[])]
        for item in self.patches:
            item.start()
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def request(self, path, body=None, headers=None):
        headers = dict(headers or {})
        if isinstance(body, dict):
            headers['Content-Type'] = 'application/json'
            body = json.dumps(body).encode()
        req = urllib.request.Request(self.url + path, data=body, headers=headers)
        try:
            response = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read())

    def upload(self, data=None, filename='fixture.wav', pid='all', headers=None):
        return self.request('/api/imports', wav_bytes() if data is None else data,
                            {'X-Filename': filename, 'X-Playlist-Id': pid, **(headers or {})})

    def test_playlist_persistence_default_dedup_and_missing_files(self):
        a, b = 'a' * 32, 'b' * 32
        pid = librarytools.edit_playlist(self.state, {'action': 'create', 'name': ' 日语学习 '}, [a, b])
        librarytools.edit_playlist(self.state, {'action': 'add', 'id': pid, 'files': [a, a, b]}, [a, b])
        self.assertEqual(librarytools.playlists(self.state, [a, b])[1]['files'], [a, b])
        self.assertEqual(librarytools.playlists(self.state, [b])[1]['files'], [b])
        self.assertEqual(librarytools.read_playlists(self.state)[0]['files'], [a, b])
        librarytools.edit_playlist(self.state, {'action': 'rename', 'id': pid, 'name': '自选'}, [a, b])
        librarytools.edit_playlist(self.state, {'action': 'remove', 'id': pid, 'files': [a]}, [a, b])
        self.assertEqual(librarytools.playlists(self.state, [a, b])[1], {'id': pid, 'name': '自选', 'files': [b]})
        for action in ['delete', 'rename', 'add', 'remove']:
            with self.assertRaises(ValueError):
                librarytools.edit_playlist(self.state, {'action': action, 'id': 'all', 'name': 'bad', 'files': [a]}, [a])
        librarytools.edit_playlist(self.state, {'action': 'delete', 'id': pid}, [a, b])
        self.assertEqual(len(librarytools.playlists(self.state, [a, b])), 1)

    def test_corrupt_playlist_is_not_overwritten(self):
        self.state.mkdir()
        path = self.state / 'playlists.json'
        path.write_text('broken')
        with self.assertRaises(ValueError):
            librarytools.edit_playlist(self.state, {'action': 'create', 'name': 'new'}, [])
        self.assertEqual(path.read_text(), 'broken')

    def test_upload_to_selected_playlist_survives_reload_and_failed_lyrics(self):
        code, result = self.request('/api/playlists', {'action': 'create', 'name': '日本語'})
        self.assertEqual(code, 200)
        pid = result['id']
        code, result = self.upload(pid=pid)
        self.assertEqual(code, 202)
        job = result['import']
        self.assertEqual(job['status'], 'completed')
        self.assertEqual(job['lyricStatus'], 'failed')
        self.assertIn('在线找歌词', job['message'])
        fid = job['fileId']
        self.assertEqual(self.request('/api/playlists')[1]['playlists'][1]['files'], [fid])
        self.assertEqual(self.request('/api/library')[1]['songs'][0]['title'], 'fixture')
        server.IMPORTS.clear()
        server.load_imports()
        self.assertEqual(server.IMPORTS[job['id']]['fileId'], fid)
        self.request('/api/playlists', {'action': 'delete', 'id': pid})
        self.assertTrue(server.find_file(fid).exists())

    def test_invalid_uploads_leave_no_audio(self):
        for filename, body, pid in [('fake.mp3', b'not audio', 'all'), ('../x.wav', b'x', 'all'),
                                     ('x.txt', b'x', 'all'), ('x.wav', b'x', 'missing')]:
            self.assertEqual(self.upload(body, filename, pid)[0], 400)
        self.assertEqual(self.upload(b'x', headers={'Content-Length': str(librarytools.MAX_IMPORT + 1)})[0], 413)
        self.assertEqual(list(self.output.rglob('*.mp3')), [])
        self.assertEqual(list(self.output.rglob('*.wav')), [])
        self.assertEqual(server.IMPORTS, {})

    def test_import_origin_and_auth_guard(self):
        self.assertEqual(self.upload(b'x', headers={'Origin': 'https://foreign.example'})[0], 403)
        with patch.object(server, 'AUTH_PASSWORD', 'password'):
            self.assertEqual(self.upload(b'x')[0], 401)
        self.assertEqual(list(self.output.rglob('*.wav')), [])

    def test_embedded_lyrics_are_preserved_without_network(self):
        from mutagen.wave import WAVE
        from mutagen.id3 import USLT
        path = Path(self.temp.name) / 'embedded.wav'
        path.write_bytes(wav_bytes())
        audio = WAVE(path)
        audio.add_tags()
        audio.tags.add(USLT(encoding=3, lang='jpn', text='[00:00]君の声'))
        audio.save()
        with patch.object(lyrics, 'candidates', side_effect=AssertionError('network not needed')):
            code, result = self.upload(path.read_bytes())
        self.assertEqual(code, 202)
        self.assertEqual(result['import']['lyricStatus'], 'existing')
        fid = result['import']['fileId']
        self.assertEqual(lyrics.load(server.find_file(fid), fid, self.state)['original'], '[00:00]君の声')

    def test_auto_fill_bilingual_and_manual_import_precedence(self):
        choice = {'id': '123', 'title': 'fixture', 'artist': '歌手', 'duration': 2}
        fetched = {'original': '[00:00]君の声', 'translation': '[00:00]你的声音'}
        with patch.object(lyrics, 'candidates', return_value=[choice]), patch.object(lyrics, 'netease_lyrics', return_value=fetched):
            result = self.upload()[1]['import']
        self.assertEqual(result['lyricStatus'], 'filled')
        raw = lyrics.load(server.find_file(result['fileId']), result['fileId'], self.state)
        self.assertEqual(raw['translation'], fetched['translation'])
        def manual_while_fetching(_):
            job = list(server.IMPORTS.values())[-1]
            lyrics.save(job['fileId'], self.state, '[00:00]手动原文', '', 'manual')
            return fetched
        with patch.object(lyrics, 'candidates', return_value=[choice]), patch.object(lyrics, 'netease_lyrics', side_effect=manual_while_fetching):
            result = self.upload()[1]['import']
        self.assertEqual(result['lyricStatus'], 'existing')
        self.assertEqual(lyrics.load(server.find_file(result['fileId']), result['fileId'], self.state)['original'], '[00:00]手动原文')

    def test_restart_interrupted_lyric_job_is_reported(self):
        result = self.upload()[1]['import']
        server.IMPORTS[result['id']]['status'] = 'checking'
        server.persist_imports()
        server.IMPORTS.clear()
        server.load_imports()
        self.assertEqual(server.IMPORTS[result['id']]['lyricStatus'], 'failed')
        self.assertIn('服务已重启', server.IMPORTS[result['id']]['message'])

    def test_player_automatic_lookup_does_not_bypass_import_ambiguity(self):
        from mutagen.wave import WAVE
        from mutagen.id3 import TPE1
        path = Path(self.temp.name) / 'tagged.wav'
        path.write_bytes(wav_bytes())
        audio = WAVE(path)
        audio.add_tags()
        audio.tags.add(TPE1(encoding=3, text='歌手'))
        audio.save()
        choice = {'id': '1', 'title': 'fixture', 'artist': '歌手', 'duration': 2}
        with patch.object(lyrics, 'candidates', return_value=[choice, {**choice, 'id': '2'}]), patch.object(lyrics, 'netease_lyrics', side_effect=AssertionError('ambiguous version must not be selected')):
            result = self.upload(path.read_bytes())[1]['import']
            code, data = self.request('/api/lyrics/' + result['fileId'] + '/lookup', {})
        self.assertEqual(result['lyricStatus'], 'failed')
        self.assertEqual(code, 200)
        self.assertEqual(len(data['candidates']), 2)

    def test_lyric_match_requires_unique_version_and_duration(self):
        meta = {'title': '青のすみか', 'artist': 'キタニタツヤ', 'duration': '00:03:16'}
        good = {'id': '1', 'title': '青のすみか', 'artist': 'キタニタツヤ', 'duration': 196}
        self.assertEqual(librarytools.exact_lyric_match(meta, [good]), good)
        for bad in [{**good, 'artist': '翻唱'}, {**good, 'duration': 230}, {**good, 'title': '青のすみか Live'}]:
            self.assertIsNone(librarytools.exact_lyric_match(meta, [bad]))
        self.assertIsNone(librarytools.exact_lyric_match(meta, [good, {**good, 'id': '2'}]))
        self.assertIsNone(librarytools.exact_lyric_match({**meta, 'artist': '本地音乐', 'duration': '—'}, [good]))
