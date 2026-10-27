import type { MetadataRoute } from "next";
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "SteelOS — مدیریت فولاد",
    short_name: "SteelOS",
    lang: "fa",
    dir: "rtl",
    start_url: "/",
    display: "standalone",
    background_color: "#f3f6fa",
    theme_color: "#102a43",
  };
}
