const {app,BrowserWindow,Menu}=require('electron');
const path=require('path');
function create(){
  const w=new BrowserWindow({width:1366,height:820,show:false,title:'اتوبنز وحدت',autoHideMenuBar:true,webPreferences:{contextIsolation:true,nodeIntegration:false,spellcheck:false}});
  Menu.setApplicationMenu(null);
  w.loadFile(path.join(__dirname,'app','index.html'));
  w.once('ready-to-show',()=>{w.maximize();w.show()});
  w.webContents.setWindowOpenHandler(()=>({action:'allow'}));
}
if(!app.requestSingleInstanceLock())app.quit();
else app.whenReady().then(create);
app.on('window-all-closed',()=>app.quit());
