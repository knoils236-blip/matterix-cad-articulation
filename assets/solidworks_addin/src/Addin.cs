// Matterix Isaac Sim Exporter: resident SolidWorks add-in.
// Adds "Tools > Matterix Isaac Sim Exporter > Export for Isaac Sim", which writes the active
// assembly's component tree, mates, materials and mass properties to <assembly>_isaacsim.json.
// The JSON is the CAD-side input for building the Isaac Sim / Matterix USD asset
// (MATTERIX Methods, Asset generation: physical properties attached to converted USD assets).
//
// C# 5 so the csc.exe shipped with Windows (.NET Framework 4.x) builds it; see build.bat.

using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using Microsoft.Win32;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;
using SolidWorks.Interop.swpublished;

namespace Matterix.SwExporter
{
    [ComVisible(true)]
    [Guid("dbe2f87d-de93-4124-b91d-6a36168fb1c1")]
    [ProgId("Matterix.SwExporter")]
    public class Addin : ISwAddin
    {
        const string Title = "Matterix Isaac Sim Exporter";
        const string Description = "Export assembly structure, mates, materials and mass properties for Isaac Sim USD";
        const int CommandGroupId = 7301;

        ISldWorks swApp;
        ICommandManager cmdMgr;

        public bool ConnectToSW(object ThisSW, int Cookie)
        {
            swApp = (ISldWorks)ThisSW;
            swApp.SetAddinCallbackInfo2(0, this, Cookie);
            cmdMgr = swApp.GetCommandManager(Cookie);

            int errors = 0;
            ICommandGroup group = cmdMgr.CreateCommandGroup2(CommandGroupId, Title, Description, Description, -1, true, ref errors);
            group.AddCommandItem2("Export for Isaac Sim", -1, Description, "Export for Isaac Sim", -1,
                "OnExport", "OnExportEnable", 0, (int)swCommandItemType_e.swMenuItem);
            group.HasToolbar = false;
            group.HasMenu = true;
            group.Activate();
            return true;
        }

        public bool DisconnectFromSW()
        {
            cmdMgr.RemoveCommandGroup(CommandGroupId);
            Marshal.ReleaseComObject(cmdMgr);
            cmdMgr = null;
            swApp = null;
            GC.Collect();
            GC.WaitForPendingFinalizers();
            return true;
        }

        // Command callbacks are looked up by name through SetAddinCallbackInfo2, so they must stay public.
        public void OnExport()
        {
            try
            {
                string summary = new Exporter(swApp).Run((ModelDoc2)swApp.ActiveDoc);
                MessageBox.Show(summary, Title, MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            catch (Exception e)  // never let an exception escape into the SolidWorks process
            {
                MessageBox.Show("Export failed:\n\n" + e, Title, MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        // 1 = enabled, 0 = disabled: only for an active assembly.
        public int OnExportEnable()
        {
            ModelDoc2 doc = (ModelDoc2)swApp.ActiveDoc;
            return doc != null && doc.GetType() == (int)swDocumentTypes_e.swDocASSEMBLY ? 1 : 0;
        }

        [ComRegisterFunction]
        public static void RegisterFunction(Type t)
        {
            string guid = "{" + t.GUID.ToString() + "}";
            using (RegistryKey k = Registry.LocalMachine.CreateSubKey(@"SOFTWARE\SolidWorks\Addins\" + guid))
            {
                k.SetValue(null, 1);  // DWORD 1: load at startup by default
                k.SetValue("Title", Title);
                k.SetValue("Description", Description);
            }
            using (RegistryKey k = Registry.CurrentUser.CreateSubKey(@"Software\SolidWorks\AddInsStartup\" + guid))
                k.SetValue(null, 1);
        }

        [ComUnregisterFunction]
        public static void UnregisterFunction(Type t)
        {
            string guid = "{" + t.GUID.ToString() + "}";
            Registry.LocalMachine.DeleteSubKey(@"SOFTWARE\SolidWorks\Addins\" + guid, false);
            Registry.CurrentUser.DeleteSubKey(@"Software\SolidWorks\AddInsStartup\" + guid, false);
        }
    }
}
