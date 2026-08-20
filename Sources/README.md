# Sources

`web/` contains the dependency-free, read-only prototype for Issue #5. From the
repository root, serve the project with:

```sh
python3 -m http.server 4173
```

Then open `http://localhost:4173/Sources/web/`. The prototype only fetches
committed synthetic JSON from `Samples/`; it has no write path or external API.
