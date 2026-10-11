'use strict';
(() => {
  if(!window.MusicdlDesktopInitial)return;
  const values={...window.MusicdlDesktopInitial};
  let scheduled=false,pending=null,revision=0,saved=0,warned=false;
  async function flush(){
    scheduled=false;
    if(pending)return;
    const current=revision,body=JSON.stringify(values);
    pending=fetch('/api/desktop/preferences',{method:'POST',headers:{'Content-Type':'application/json'},body,keepalive:true});
    try{
      const response=await pending;if(!response.ok)throw new Error('save failed');saved=current;warned=false;
    }catch{
      if(!warned){warned=true;const node=document.createElement('div');node.className='toast error';node.textContent='桌面记录暂时无法写入，请检查数据目录权限。';document.querySelector('#toasts')?.append(node);setTimeout(()=>node.remove(),6000);}
    }finally{pending=null;if(revision>current)flush();}
  }
  window.MusicdlDesktopStorage={
    getItem(key){return Object.hasOwn(values,key)?values[key]:null;},
    setItem(key,value){
      if(!key.startsWith('musicdl.'))return;
      values[key]=String(value);revision++;
      if(!scheduled){scheduled=true;queueMicrotask(flush);}
    },
    snapshot(){return {...values};}
  };
  window.addEventListener('pagehide',()=>{if(saved!==revision)navigator.sendBeacon('/api/desktop/preferences',new Blob([JSON.stringify(values)],{type:'application/json'}));});
  window.addEventListener('pywebviewready',()=>{
    const button=document.querySelector('#openDataDirectory');
    if(button){button.hidden=false;button.addEventListener('click',()=>window.pywebview.api.open_data_directory().catch(()=>{}));}
  });
})();
