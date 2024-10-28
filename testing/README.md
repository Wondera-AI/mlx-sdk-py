create new testing crate in py project

```bash
cargo generate --git https://<token>@github.com/alexlatif/testing-py-from-rust.git
```

create run script in pyproject.toml
```toml
[tool.pdm.scripts]
test = "cargo run --manifest-path testing/Cargo.toml"
```

run tests
```bash
pdm run test
```