mod constants;
mod contract_generator;
mod errors;
mod filesystem;
mod generator;
mod go_generator;
mod metadata;
mod module_types;
mod project;
mod python_generator;
mod readme_generator;
mod rust_generator;
mod template;
mod template_selector;
mod validator;

use clap::Parser;
use std::path::PathBuf;

#[derive(Parser, Debug)]
#[command(name = "specgen")]
#[command(version)]
#[command(about = "Atlas AI Specification Generator")]
struct Cli {
    #[arg(short, long)]
    metadata: PathBuf,

    #[arg(short, long)]
    output: PathBuf,

    /// Templates directory (defaults to ./templates relative to binary)
    #[arg(long)]
    templates: Option<PathBuf>,
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    let metadata = metadata::Metadata::load(&cli.metadata)?;
    validator::validate(&metadata)?;

    let templates_dir = cli.templates.unwrap_or_else(|| {
        std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|d| d.join("templates")))
            .unwrap_or_else(|| PathBuf::from("templates"))
    });

    let result = generator::generate(&metadata.module, &cli.output, &templates_dir)?;

    println!("✅ SpecGen completed successfully");
    println!("   Module:     {}", metadata.module.name);
    println!("   Language:   {}", metadata.module.language);
    println!("   Artifact:   {}", metadata.module.artifact);
    println!("   Output:     {}", cli.output.display());
    println!("   Files:      {}", result.files_written.len());
    for f in &result.files_written {
        println!("     → {}", f.display());
    }

    Ok(())
}
