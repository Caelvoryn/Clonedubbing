using System;
using System.IO;
using System.Reflection;
using System.Windows.Forms;
class Installer {
 [STAThread] static void Main(){try{
  string dir=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"UnifiedVoice");Directory.CreateDirectory(dir);
  string exe=Path.Combine(dir,"综合声线配音.exe");
  using(Stream source=Assembly.GetExecutingAssembly().GetManifestResourceStream("client.exe"))using(Stream target=File.Create(exe)){source.CopyTo(target);}
  string desktop=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),"综合声线配音.url");
  File.WriteAllText(desktop,"[InternetShortcut]\r\nURL="+new Uri(exe).AbsoluteUri+"\r\n");
  MessageBox.Show("安装完成。桌面已创建入口；打开后填写配音服务器地址。","综合声线配音安装");
 }catch(Exception ex){MessageBox.Show(ex.Message,"安装失败");}}
}
