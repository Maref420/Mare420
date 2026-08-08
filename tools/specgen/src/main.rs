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

fn main() {
    let cli = Cli::parse();

    println!("SpecGen");
    println!("Metadata : {}", cli.metadata.display());
    println!("Output   : {}", cli.output.display());
}
