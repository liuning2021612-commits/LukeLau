/*
 * geom2dwg.c: write a plain-text geometry file (from image_to_cad.py --geom)
 * as an R2000 DWG using the LibreDWG API.
 *
 * Input lines:
 *   E xmin ymin xmax ymax                 drawing extents
 *   L name color                          layer (ACI color)
 *   P layer closed n x1 y1 ... xn yn      lightweight polyline
 *   N layer x1 y1 x2 y2                   line
 *   T layer x y height rot_deg text       middle-centred text
 *
 * Build: cc -O2 geom2dwg.c -I<libredwg>/include -L<libredwg>/lib -lredwg -lm
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dwg.h>
#include <dwg_api.h>

#define MAX_LAYERS 32

static struct
{
  char name[64];
  BITCODE_RLL handle;
} layers[MAX_LAYERS];
static int num_layers;

static void
use_layer (Dwg_Data *dwg, const char *name)
{
  for (int i = 0; i < num_layers; i++)
    if (!strcmp (layers[i].name, name))
      {
        dwg->header_vars.CLAYER
            = dwg_add_handleref (dwg, 5, layers[i].handle, NULL);
        return;
      }
  fprintf (stderr, "unknown layer %s\n", name);
  exit (1);
}

int
main (int argc, char **argv)
{
  if (argc != 3)
    {
      fprintf (stderr, "usage: %s GEOMFILE OUT.dwg\n", argv[0]);
      return 1;
    }
  FILE *f = fopen (argv[1], "r");
  if (!f)
    {
      perror (argv[1]);
      return 1;
    }

  Dwg_Data *dwg = dwg_new_Document (R_2000, 0 /* metric */, 0);
  dwg->header_vars.INSUNITS = 4; /* millimetres */
  dwg->header_vars.MEASUREMENT = 1;
  BITCODE_H layer0 = dwg->header_vars.CLAYER;
  BITCODE_RLL ltype_continuous = dwg->header_vars.LTYPE_CONTINUOUS
                                     ? dwg->header_vars.LTYPE_CONTINUOUS->absolute_ref
                                     : 0x16;
  Dwg_Object *mspace = dwg_model_space_object (dwg);
  Dwg_Object_BLOCK_HEADER *hdr = mspace->tio.object->tio.BLOCK_HEADER;

  size_t cap = 1 << 20;
  char *line = malloc (cap);
  dwg_point_2d *pts = malloc (sizeof (dwg_point_2d) * 65536);
  long npoly = 0;
  int err;

  while (fgets (line, (int)cap, f))
    {
      char name[64];
      char *p = line;
      int n;
      switch (line[0])
        {
        case 'E':
          {
            double x0, y0, x1, y1;
            sscanf (line + 2, "%lf %lf %lf %lf", &x0, &y0, &x1, &y1);
            dwg->header_vars.EXTMIN = (BITCODE_3BD){ x0, y0, 0 };
            dwg->header_vars.EXTMAX = (BITCODE_3BD){ x1, y1, 0 };
            dwg->header_vars.LIMMIN = (BITCODE_2DPOINT){ x0, y0 };
            dwg->header_vars.LIMMAX = (BITCODE_2DPOINT){ x1, y1 };
            Dwg_Object_VPORT *vp = dwg_add_VPORT (dwg, "*Active");
            double w = (x1 - x0) * 1.05, h = (y1 - y0) * 1.05;
            vp->VIEWCTR.x = (x0 + x1) / 2;
            vp->VIEWCTR.y = (y0 + y1) / 2;
            vp->VIEWSIZE = h;
            vp->view_width = w;
            vp->aspect_ratio = w / h;
            vp->GRIDUNIT.x = vp->GRIDUNIT.y = 1000.0;
            vp->SNAPUNIT.x = vp->SNAPUNIT.y = 1000.0;
            break;
          }
        case 'L':
          {
            int color;
            sscanf (line + 2, "%63s %d", name, &color);
            Dwg_Object_LAYER *lay = dwg_add_LAYER (dwg, name);
            lay->color.index = (BITCODE_BS)color;
            lay->ltype = dwg_add_handleref (dwg, 5, ltype_continuous, NULL);
            lay->linewt = 0x1d; /* default lineweight */
            Dwg_Object *o = dwg_obj_generic_to_object (lay, &err);
            strcpy (layers[num_layers].name, name);
            layers[num_layers++].handle = o->handle.value;
            break;
          }
        case 'P':
          {
            int closed;
            p += 2;
            int used;
            sscanf (p, "%63s %d %d%n", name, &closed, &n, &used);
            p += used;
            for (int i = 0; i < n; i++)
              pts[i].x = strtod (p, &p), pts[i].y = strtod (p, &p);
            use_layer (dwg, name);
            Dwg_Entity_LWPOLYLINE *pl = dwg_add_LWPOLYLINE (hdr, n, pts);
            if (closed)
              pl->flag |= 512;
            npoly++;
            break;
          }
        case 'N':
          {
            dwg_point_3d a = { 0 }, b = { 0 };
            sscanf (line + 2, "%63s %lf %lf %lf %lf", name, &a.x, &a.y, &b.x,
                    &b.y);
            use_layer (dwg, name);
            dwg_add_LINE (hdr, &a, &b);
            break;
          }
        case 'T':
          {
            dwg_point_3d ins = { 0 };
            double height, rot;
            sscanf (line + 2, "%63s %lf %lf %lf %lf %n", name, &ins.x, &ins.y,
                    &height, &rot, &n);
            char *text = line + 2 + n;
            text[strcspn (text, "\r\n")] = 0;
            use_layer (dwg, name);
            Dwg_Entity_TEXT *t = dwg_add_TEXT (hdr, text, &ins, height);
            t->rotation = rot * M_PI / 180.0;
            t->width_factor = 1.0;
            t->horiz_alignment = 1; /* center */
            t->vert_alignment = 2;  /* middle */
            t->alignment_pt.x = ins.x;
            t->alignment_pt.y = ins.y;
            break;
          }
        }
    }
  fclose (f);
  dwg->header_vars.CLAYER = layer0;

  int rc = dwg_write_file (argv[2], dwg);
  printf ("%ld polylines, %d layers -> %s (rc=%d)\n", npoly, num_layers,
          argv[2], rc);
  return rc >= DWG_ERR_CRITICAL;
}
