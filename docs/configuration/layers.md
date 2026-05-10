# Layers

Layer configuration files define map layers to build. They reference source IDs from source config files.

```yaml
bounds:
  west: 6.5
  east: 7.5
  south: 46.5
  north: 47.0

layers:
  my_layer:
    name: "My Layer"
    description: "Layer description"
    type: raster
    source: my_wmts
    wmts_layer: my_wmts_layer_name
    zoom_levels: [10, 12, 14]
    exporter: garmin_img
    output: my_layer.img
```
