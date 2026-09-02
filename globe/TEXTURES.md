# Textures

`build_earth.py` expects three equirectangular maps next to it, each resized to 2048×1024 on load:

| file | content |
|---|---|
| `earth_clean.bin` | daytime surface colour, no clouds |
| `earth_night.bin` | city lights on black |
| `clouds.bin` | cloud cover, white on black |

They are ordinary JPEGs (the `.bin` name only keeps them out of image indexers). They are not in this
repo; bring your own. NASA's Blue Marble (day), Black Marble (night lights) and cloud composites are
public domain and are the usual choice.
