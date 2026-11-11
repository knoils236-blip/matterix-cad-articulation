// Walks the active assembly and writes <assembly>_isaacsim.json (UTF-8, SI units).
//   components: instance tree, file/config, suppressed/fixed/visible/flexible, MathTransform.ArrayData
//   mates:      every mate in the top assembly and in each sub-assembly instance, with entity geometry
//   parts:      per (file, referenced config): material, density, mass, volume, area, COM, inertia, custom properties

using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

namespace Matterix.SwExporter
{
    class Exporter
    {
        // IMassProperty.GetMomentOfInertia: 0 = about the centre of mass, aligned with the part axes.
        const int MomentAboutCenterOfMass = 0;

        readonly ISldWorks swApp;
        readonly List<string> comps = new List<string>();
        readonly List<string> mates = new List<string>();
        readonly List<string> parts = new List<string>();
        readonly HashSet<string> seenParts = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        public Exporter(ISldWorks swApp)
        {
            this.swApp = swApp;
        }

        public string Run(ModelDoc2 doc)
        {
            AssemblyDoc assy = (AssemblyDoc)doc;
            assy.ResolveAllLightWeightComponents(false);

            CollectMates((Feature)doc.FirstFeature(), "");
            object top = assy.GetComponents(true);
            if (top != null)
                foreach (Component2 c in (IEnumerable)top) WalkComp(c, "");

            string asmPath = doc.GetPathName();
            StringBuilder json = new StringBuilder();
            json.Append("{\n");
            json.Append("\"format\": \"matterix-sw-export-v1\",\n");
            json.Append("\"solidworks\": " + Q(swApp.RevisionNumber()) + ",\n");
            json.Append("\"exportedAt\": " + Q(DateTime.Now.ToString("s", CultureInfo.InvariantCulture)) + ",\n");
            json.Append("\"assembly\": " + Q(asmPath) + ",\n");
            json.Append("\"configuration\": " + Q(doc.ConfigurationManager.ActiveConfiguration.Name) + ",\n");
            json.Append("\"units\": \"SI (m, rad, kg, kg/m^3, kg*m^2)\",\n");
            json.Append("\"components\": [\n" + Join(comps) + "],\n");
            json.Append("\"mates\": [\n" + Join(mates) + "],\n");
            json.Append("\"parts\": [\n" + Join(parts) + "]\n}\n");

            string outPath = Path.Combine(Path.GetDirectoryName(asmPath), Path.GetFileNameWithoutExtension(asmPath) + "_isaacsim.json");
            File.WriteAllText(outPath, json.ToString(), new UTF8Encoding(false));
            return "Exported " + comps.Count + " components, " + mates.Count + " mates, " + parts.Count + " parts to:\n\n" + outPath;
        }

        void WalkComp(Component2 comp, string parentName)
        {
            string path = comp.GetPathName();
            string name = comp.Name2;
            bool isAssy = path.EndsWith(".sldasm", StringComparison.OrdinalIgnoreCase);
            bool suppressed = comp.IsSuppressed();

            string s = "{\"name\": " + Q(name) + ", \"parent\": " + Q(parentName) +
                ", \"path\": " + Q(path) + ", \"config\": " + Q(comp.ReferencedConfiguration) +
                ", \"isAssembly\": " + B(isAssy) + ", \"suppressed\": " + B(suppressed) +
                ", \"fixed\": " + B(comp.IsFixed()) +
                ", \"visible\": " + B(comp.Visible == (int)swComponentVisibilityState_e.swComponentVisible);
            if (isAssy) s += ", \"flexible\": " + B(comp.Solving == (int)swComponentSolvingOption_e.swComponentFlexibleSolving);
            MathTransform xf = comp.Transform2;
            if (xf != null) s += ", \"transform\": " + NumArr(xf.ArrayData);
            comps.Add(s + "}");
            if (suppressed) return;

            if (isAssy)
                CollectMates((Feature)comp.FirstFeature(), name);
            else if (seenParts.Add(path + "|" + comp.ReferencedConfiguration))
                AddPart(comp);

            object children = comp.GetChildren();
            if (children != null)
                foreach (Component2 c in (IEnumerable)children) WalkComp(c, name);
        }

        void CollectMates(Feature feat, string owner)
        {
            while (feat != null)
            {
                if (feat.GetTypeName2() == "MateGroup") WalkMateFolder((Feature)feat.GetFirstSubFeature(), owner);
                feat = (Feature)feat.GetNextFeature();
            }
        }

        // MateGroup may contain user folders; recurse into anything that is not a mate.
        void WalkMateFolder(Feature feat, string owner)
        {
            while (feat != null)
            {
                Mate2 mate = feat.GetSpecificFeature2() as Mate2;
                string typeName = feat.GetTypeName2();
                if (mate != null)
                    AddMate(feat, mate, owner);
                else if (feat.IsSuppressed() && typeName.Contains("Mate"))
                    mates.Add("{\"owner\": " + Q(owner) + ", \"feature\": " + Q(feat.Name) +
                        ", \"featureType\": " + Q(typeName) + ", \"suppressed\": true}");
                else
                    WalkMateFolder((Feature)feat.GetFirstSubFeature(), owner);
                feat = (Feature)feat.GetNextSubFeature();
            }
        }

        void AddMate(Feature feat, Mate2 m, string owner)
        {
            string s = "{\"owner\": " + Q(owner) + ", \"feature\": " + Q(feat.Name) +
                ", \"featureType\": " + Q(feat.GetTypeName2()) + ", \"suppressed\": " + B(feat.IsSuppressed()) +
                ", \"type\": " + m.Type + ", \"typeName\": " + Q(((swMateType_e)m.Type).ToString()) +
                ", \"alignment\": " + m.Alignment + ", \"flipped\": " + B(m.Flipped);

            // Distance / angle / limit (value, max, min) / gear values live on the mate's dimensions.
            List<string> dims = new List<string>();
            DisplayDimension dd = (DisplayDimension)feat.GetFirstDisplayDimension();
            while (dd != null)
            {
                Dimension d = dd.GetDimension2(0);
                dims.Add("{\"name\": " + Q(d.FullName) + ", \"value\": " + Num(d.SystemValue) + "}");
                dd = (DisplayDimension)feat.GetNextDisplayDimension(dd);
            }
            s += ", \"dimensions\": [" + string.Join(", ", dims) + "]";
            // Limit mates keep their travel range outside the display dimensions (SI units).
            if (feat.GetTypeName2().StartsWith("MateLimit"))
                s += ", \"minimum\": " + Num(m.MinimumVariation) + ", \"maximum\": " + Num(m.MaximumVariation);

            // EntityParams: point (3), direction (3), radius1, radius2 of the mated face/edge/axis/point.
            List<string> ents = new List<string>();
            for (int i = 0; i < m.MateEntityCount; i++)
            {
                MateEntity2 e = m.MateEntity(i);
                Component2 refComp = e.ReferenceComponent;
                ents.Add("{\"component\": " + Q(refComp == null ? "" : refComp.Name2) +
                    ", \"refType\": " + e.ReferenceType2 +
                    ", \"params\": " + NumArr(e.EntityParams) + "}");
            }
            mates.Add(s + ", \"entities\": [" + string.Join(", ", ents) + "]}");
        }

        void AddPart(Component2 comp)
        {
            ModelDoc2 mdoc = (ModelDoc2)comp.GetModelDoc2();
            if (mdoc == null) return;
            string config = comp.ReferencedConfiguration;
            string activeConfig = mdoc.ConfigurationManager.ActiveConfiguration.Name;
            string db;
            string material = ((PartDoc)mdoc).GetMaterialPropertyName2(config, out db);

            string s = "{\"path\": " + Q(comp.GetPathName()) + ", \"config\": " + Q(config) +
                ", \"material\": " + Q(material) + ", \"materialDb\": " + Q(db) +
                ", \"massConfig\": " + Q(activeConfig);
            // Mass properties are evaluated in the part's active configuration (massConfig);
            // a different referenced config is flagged for the USD builder rather than switched here.
            MassProperty mp = (MassProperty)mdoc.Extension.CreateMassProperty();
            if (mp != null)
                s += ", \"density\": " + Num(mp.Density) + ", \"mass\": " + Num(mp.Mass) +
                    ", \"volume\": " + Num(mp.Volume) + ", \"surfaceArea\": " + Num(mp.SurfaceArea) +
                    ", \"centerOfMass\": " + NumArr(mp.CenterOfMass) +
                    ", \"inertiaAtCom\": " + NumArr(mp.GetMomentOfInertia(MomentAboutCenterOfMass));
            s += ", \"properties\": " + Properties(mdoc.Extension.get_CustomPropertyManager("")) +
                ", \"configProperties\": " + Properties(mdoc.Extension.get_CustomPropertyManager(config));
            parts.Add(s + "}");
        }

        static string Properties(CustomPropertyManager mgr)
        {
            object names = mgr.GetNames();
            if (names == null) return "{}";
            List<string> items = new List<string>();
            foreach (string n in (IEnumerable)names)
            {
                string raw, resolved;
                mgr.Get4(n, false, out raw, out resolved);
                items.Add(Q(n) + ": " + Q(resolved));
            }
            return "{" + string.Join(", ", items) + "}";
        }

        static string Q(string s)
        {
            if (s == null) return "null";
            StringBuilder b = new StringBuilder("\"");
            foreach (char c in s)
            {
                if (c == '"') b.Append("\\\"");
                else if (c == '\\') b.Append("\\\\");
                else if (c < 0x20) b.Append("\\u" + ((int)c).ToString("x4"));
                else b.Append(c);
            }
            return b.Append('"').ToString();
        }

        static string B(bool v) { return v ? "true" : "false"; }

        static string Num(double x)
        {
            if (double.IsNaN(x) || double.IsInfinity(x)) return "null";
            return x.ToString("R", CultureInfo.InvariantCulture);
        }

        static string NumArr(object v)
        {
            IEnumerable e = v as IEnumerable;
            if (e == null) return "null";
            List<string> items = new List<string>();
            foreach (object x in e) items.Add(Num(Convert.ToDouble(x, CultureInfo.InvariantCulture)));
            return "[" + string.Join(", ", items) + "]";
        }

        static string Join(List<string> items)
        {
            return items.Count == 0 ? "" : string.Join(",\n", items) + "\n";
        }
    }
}
