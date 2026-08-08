mod errors;
mod metadata;
mod module_types;
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
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    let metadata = metadata::Metadata::load(&cli.metadata)?;

    validator::validate(&metadata)?;

    println!("SpecGen");
    println!("Metadata : {}", cli.metadata.display());
    println!("Output   : {}", cli.output.display());
    println!("Module   : {}", metadata.module.name);
    println!("Artifact : {}", metadata.module.artifact);
    println!("Language : {}", metadata.module.language);
    println!("Profile  : {}", metadata.module.profile);
    println!("Owner    : {}", metadata.module.owner);
    println!("Valid    : yes");

    Ok(())
}
