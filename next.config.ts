import type { NextConfig } from "next";

// File-tracing rules for the city-wide data layout.
//
// Parcel shards (data/shards, ~426 MB), ward COGs (data/cogs, ~200 MB) and
// per-ward downloads (data/downloads, ~600 MB) are NEVER bundled: in
// production every route fetches them over HTTP (jsDelivr over this repo,
// with a raw.githubusercontent.com fallback for >20 MB files). The file
// tracer cannot statically resolve the dynamic shard/cog paths, so without
// these excludes it globs the whole data/ tree into the functions (measured
// 9.9 GB for /api/download). `next dev` does not use file tracing, so the
// local data/shards + data/cogs dir fallbacks keep working in development.
//
// Bundled with the functions: data/city_boundary.json (58 KB, honest 404s)
// and data/calibration_lidar.json (4 KB), both read via literal paths.
//
// Build note: package.json runs `next build --webpack`, not Turbopack.
// Turbopack's build OOMs above 5 GB on this app's graph (sharp + geotiff);
// webpack builds cleanly in ~40 s and keeps the same route output.

const DATA_BUNDLED = ["./data/city_boundary.json", "./data/calibration_lidar.json"];

const nextConfig: NextConfig = {
  outputFileTracingExcludes: {
    "/api/download": ["./data/**/*"],
    "/api/v1/screen": ["./data/shards/**/*", "./data/cogs/**/*", "./data/downloads/**/*"],
    "/api/v1/parcel-map": ["./data/shards/**/*", "./data/cogs/**/*", "./data/downloads/**/*"],
    "/mcp": ["./data/shards/**/*", "./data/cogs/**/*", "./data/downloads/**/*"],
    "/[lang]": ["./data/shards/**/*", "./data/cogs/**/*", "./data/downloads/**/*"],
  },
  outputFileTracingIncludes: {
    "/api/v1/screen": DATA_BUNDLED,
    "/api/v1/parcel-map": DATA_BUNDLED,
    "/mcp": DATA_BUNDLED,
    "/[lang]": DATA_BUNDLED,
  },
};

export default nextConfig;
