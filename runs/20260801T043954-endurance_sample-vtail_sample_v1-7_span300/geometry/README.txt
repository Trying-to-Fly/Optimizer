Buildable geometry for this run.

Units are metres, aircraft frame: +x aft from the nose datum, +y starboard,
+z up. Surfaces with symmetric = True store only the STARBOARD half; mirror
about y = 0 for the port side.

stations.csv
    The loft definition — one row per section. Leading- and trailing-edge
    points, chord, twist and the airfoil each section uses. Enough on its own
    to rebuild the surface in CAD: place the LE points, set each chord and
    twist, apply the named airfoil, loft between stations in order.

sections_3d.csv
    The curves themselves. Each section's airfoil outline already scaled,
    twisted and positioned, as an ordered point list. Import per
    (surface, station) as a closed polyline and loft, or cut ribs directly.
    Point order follows the airfoil file: trailing edge, over the top, around
    the leading edge, back along the bottom.

Both are generated from the same geometry the solver analysed, so what you
build is what was evaluated.
