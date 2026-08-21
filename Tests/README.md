# Tests

Run the canonical dependency-free validation from the repository root:

```sh
sh Tests/run.sh
```

`run.sh` parses every JSON file under `Samples/` and runs each
`Tests/*.test.sh` script. New dependency-free shell tests can therefore join the
standard local and GitHub Actions checks by following that filename pattern.

`read-only-ui.test.sh` validates the synthetic trip contract and confirms that
the static prototype contains no network write or external-service path.
