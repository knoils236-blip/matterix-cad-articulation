// Installer for the Matterix Isaac Sim Exporter add-in.
//   MatterixSwExporterSetup.exe              install / update
//   MatterixSwExporterSetup.exe /uninstall   remove
// The add-in DLL is embedded in this exe. Install copies it to Program Files and registers it with
// the .NET Framework RegAsm (its ComRegisterFunction writes the SolidWorks add-in registry keys).

using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

static class Setup
{
    const string Title = "Matterix Isaac Sim Exporter Setup";
    const string DllName = "MatterixSwExporter.dll";

    [STAThread]
    static int Main(string[] args)
    {
        try
        {
            bool uninstall = args.Length > 0 && args[0].Equals("/uninstall", StringComparison.OrdinalIgnoreCase);
            if (Process.GetProcessesByName("SLDWORKS").Length > 0)
            {
                Show("Please close SolidWorks first, then run this setup again.", MessageBoxIcon.Warning);
                return 1;
            }
            string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Matterix", "SwExporter");
            string dll = Path.Combine(dir, DllName);

            if (uninstall)
            {
                if (File.Exists(dll)) RegAsm(dll, "/unregister");
                if (Directory.Exists(dir)) Directory.Delete(dir, true);
                Show("Uninstalled.", MessageBoxIcon.Information);
                return 0;
            }

            Directory.CreateDirectory(dir);
            using (Stream src = Assembly.GetExecutingAssembly().GetManifestResourceStream(DllName))
            using (FileStream dst = File.Create(dll))
                src.CopyTo(dst);
            RegAsm(dll, "/codebase");
            Show("Installed to:\n" + dir + "\n\nStart SolidWorks and open an assembly, then use\n" +
                 "Tools > Matterix Isaac Sim Exporter > Export for Isaac Sim.\n\n" +
                 "If the menu is missing, enable it under Tools > Add-Ins.", MessageBoxIcon.Information);
            return 0;
        }
        catch (Exception e)  // top level of a double-clicked installer: report instead of crashing silently
        {
            Show("Setup failed:\n\n" + e, MessageBoxIcon.Error);
            return 1;
        }
    }

    static void RegAsm(string dll, string option)
    {
        string exe = Path.Combine(Environment.GetEnvironmentVariable("WINDIR"), @"Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe");
        ProcessStartInfo info = new ProcessStartInfo(exe, "\"" + dll + "\" " + option);
        info.UseShellExecute = false;
        info.CreateNoWindow = true;
        info.RedirectStandardOutput = true;
        info.RedirectStandardError = true;
        using (Process p = Process.Start(info))
        {
            string output = p.StandardOutput.ReadToEnd() + p.StandardError.ReadToEnd();
            p.WaitForExit();
            if (p.ExitCode != 0) throw new Exception("RegAsm " + option + " failed:\n" + output);
        }
    }

    static void Show(string text, MessageBoxIcon icon)
    {
        MessageBox.Show(text, Title, MessageBoxButtons.OK, icon);
    }
}
