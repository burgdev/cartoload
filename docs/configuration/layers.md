# Layers

Layer configuration files define map layers to build. They reference source IDs from source config files.

```yaml
bounds:
  west: 5.96
  east: 10.49
  south: 45.82
  north: 47.81

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
