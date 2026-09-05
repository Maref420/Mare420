//! Template loading and variable substitution.
//!
//! Templates use `{variable}` placeholders replaced at generation time.
//! Unknown variables are left as-is (fail-safe, not fail-fast) so that
//! language-specific syntax like `fmt.Sprintf("%s", x)` is preserved.

use std::collections::HashMap;
use std::fs;
use std::path::Path;

use crate::errors::{SpecgenError, SpecgenResult};

/// Loads a template file from disk.
pub fn load_template(path: &Path) -> SpecgenResult<String> {
    fs::read_to_string(path).map_err(|source| SpecgenError::TemplateRead {
        path: path.to_path_buf(),
        source,
    })
}

/// Replaces `{key}` placeholders in the template with values from the map.
///
/// Only keys present in the map are substituted. This preserves
/// language-native format strings (e.g., Rust `{}`, Python f-strings).
pub fn render(template: &str, vars: &HashMap<String, String>) -> String {
    let mut result = template.to_string();
    for (key, value) in vars {
        let placeholder = format!("{{{}}}", key);
        result = result.replace(&placeholder, value);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn renders_known_variables() {
        let tpl = "Hello {name}, welcome to {project}!";
        let mut vars = HashMap::new();
        vars.insert("name".into(), "Atlas".into());
        vars.insert("project".into(), "AI".into());
        assert_eq!(render(tpl, &vars), "Hello Atlas, welcome to AI!");
    }

    #[test]
    fn preserves_unknown_placeholders() {
        let tpl = "fmt.Println(\"{}\", {value})";
        let mut vars = HashMap::new();
        vars.insert("value".into(), "42".into());
        assert_eq!(render(tpl, &vars), "fmt.Println(\"{}\", 42)");
    }

    #[test]
    fn empty_vars_returns_template_unchanged() {
        let tpl = "no changes {here}";
        let vars = HashMap::new();
        assert_eq!(render(tpl, &vars), tpl);
    }
}
