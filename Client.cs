using System;
using System.IO;
using System.Diagnostics;
using System.Windows.Forms;
class Client {
 [STAThread] static void Main(){
  Application.EnableVisualStyles();
  string dir=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"UnifiedVoice"); Directory.CreateDirectory(dir);
  string file=Path.Combine(dir,"server.txt");
  Form f=new Form{Text="综合声线配音",Width=470,Height=180,StartPosition=FormStartPosition.CenterScreen};
  TextBox url=new TextBox{Left=20,Top=35,Width=410,Text=File.Exists(file)?File.ReadAllText(file):"http://127.0.0.1:7865"};
  f.Controls.Add(new Label{Left=20,Top=10,Width=410,Text="服务器地址（向部署者获取）"});f.Controls.Add(url);
  Button b=new Button{Left=20,Top=75,Width=410,Text="保存并打开配音工作台"};f.Controls.Add(b);
  b.Click+=(s,e)=>{Uri uri;if(!Uri.TryCreate(url.Text.Trim(),UriKind.Absolute,out uri)||(uri.Scheme!="http"&&uri.Scheme!="https")){MessageBox.Show("请输入http或https服务器地址");return;}File.WriteAllText(file,uri.AbsoluteUri);Process.Start(new ProcessStartInfo(uri.AbsoluteUri){UseShellExecute=true});};
  Application.Run(f);
 }
}
