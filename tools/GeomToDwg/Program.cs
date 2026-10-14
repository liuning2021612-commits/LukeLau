// Writes the plain-text geometry from image_to_cad.py --geom as an
// AutoCAD 2018 (AC1032) DWG, the native format of AutoCAD 2018-2025.
// Input lines:
//   E xmin ymin xmax ymax                 drawing extents
//   L name color                          layer (ACI color)
//   P layer closed n x1 y1 ... xn yn      lightweight polyline
//   N layer x1 y1 x2 y2                   line
//   T layer x y height rot_deg text       middle-centred text
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using ACadSharp;
using ACadSharp.Entities;
using ACadSharp.Header;
using ACadSharp.IO;
using ACadSharp.Tables;
using ACadSharp.Types.Units;
using CSMath;

if (args.Length == 2 && args[0] == "--check")
{
    // Read a DWG back and summarise it, to verify a written file.
    var back = DwgReader.Read(args[1]);
    Console.WriteLine($"version {back.Header.Version}, {back.Entities.Count} entities, " +
                      $"layers: {string.Join(", ", System.Linq.Enumerable.Select(back.Layers, l => l.Name))}");
    return 0;
}
if (args.Length != 2)
{
    Console.Error.WriteLine("usage: GeomToDwg GEOMFILE OUT.dwg");
    return 1;
}

var inv = CultureInfo.InvariantCulture;
double D(string s) => double.Parse(s, inv);

var doc = new CadDocument(ACadVersion.AC1032);
doc.Header.InsUnits = UnitsType.Millimeters;
doc.Header.MeasurementUnits = MeasurementUnits.Metric;
var layers = new Dictionary<string, Layer>();
int polylines = 0;

foreach (var raw in File.ReadLines(args[0]))
{
    var f = raw.Split(' ', StringSplitOptions.RemoveEmptyEntries);
    if (f.Length == 0) continue;
    switch (f[0])
    {
        case "E":
            doc.Header.ModelSpaceExtMin = new XYZ(D(f[1]), D(f[2]), 0);
            doc.Header.ModelSpaceExtMax = new XYZ(D(f[3]), D(f[4]), 0);
            break;
        case "L":
            var layer = new Layer(f[1]) { Color = new Color(short.Parse(f[2])) };
            doc.Layers.Add(layer);
            layers[f[1]] = layer;
            break;
        case "P":
            int n = int.Parse(f[3]);
            var pl = new LwPolyline { Layer = layers[f[1]], IsClosed = f[2] == "1" };
            for (int i = 0; i < n; i++)
                pl.Vertices.Add(new LwPolyline.Vertex(new XY(D(f[4 + 2 * i]), D(f[5 + 2 * i]))));
            doc.Entities.Add(pl);
            polylines++;
            break;
        case "N":
            doc.Entities.Add(new Line
            {
                Layer = layers[f[1]],
                StartPoint = new XYZ(D(f[2]), D(f[3]), 0),
                EndPoint = new XYZ(D(f[4]), D(f[5]), 0),
            });
            break;
        case "T":
            var pt = new XYZ(D(f[2]), D(f[3]), 0);
            doc.Entities.Add(new TextEntity
            {
                Layer = layers[f[1]],
                Value = string.Join(' ', f[6..]),
                Height = D(f[4]),
                Rotation = D(f[5]) * Math.PI / 180.0,
                InsertPoint = pt,
                AlignmentPoint = pt,
                HorizontalAlignment = TextHorizontalAlignment.Center,
                VerticalAlignment = TextVerticalAlignmentType.Middle,
            });
            break;
    }
}

DwgWriter.Write(args[1], doc);
Console.WriteLine($"{polylines} polylines, {layers.Count} layers -> {args[1]} (AC1032 / AutoCAD 2018 format)");
return 0;
