## ADDED Requirements

### Requirement: Products section
The config loader SHALL accept a `products:` section as a dict of product definitions, where each key is a slug and each value is a dict with optional `name`, `price`, `currency`, `token_max_downloads`, `token_expiry_days`, `sort_order`, and `targets` fields.

#### Scenario: Products section parsed
- **WHEN** a config file contains a `products:` section with valid entries
- **THEN** the loader SHALL return `config.products` as `dict[str, ProductConfig]`

#### Scenario: Products section omitted
- **WHEN** a config file does not contain a `products:` section
- **THEN** the loader SHALL return `config.products` as an empty dict

### Requirement: Product target reference validation
The loader SHALL validate that all target slugs referenced in product entries exist in `config.targets`.

#### Scenario: Valid product target references
- **WHEN** a product references target slugs that exist in `config.targets`
- **THEN** the loader SHALL accept the config without error

#### Scenario: Invalid product target reference
- **WHEN** a product references a target slug that does not exist in `config.targets`
- **THEN** the loader SHALL raise a `ValueError` listing the unresolved references

### Requirement: Products merge across includes
Products from included files SHALL be merged with last-file-wins semantics.

#### Scenario: Products merged from includes
- **WHEN** a main config includes a file with products and also defines products
- **THEN** the loader SHALL merge all products, with later definitions winning on conflicts

### Requirement: ProductConfig defaults
All `ProductConfig` fields SHALL have sensible defaults matching the server model defaults.

#### Scenario: Minimal product entry
- **WHEN** a product entry specifies only `targets: [slug]`
- **THEN** the loader SHALL default `name` to the slug, `price` to `0.0`, `currency` to `"CHF"`, `token_max_downloads` to `5`, `token_expiry_days` to `30`, and `sort_order` to `0`
