# Adding Exporters

cartoload uses a pluggable exporter architecture. To add a new exporter:

1. Create a new file in `src/cartoload/exporters/`
2. Subclass `BaseExporter` from `base.py`
3. Implement the `export()` method
4. Register the exporter in the CLI

Not yet documented in detail.
