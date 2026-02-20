#!/usr/bin/env python3
# /// script
# dependencies = [
#   "pinecone>=8.0.0",
#   "typer>=0.15.0",
# ]
# ///

import os
import typer
from pinecone import Pinecone

app = typer.Typer()

@app.command()
def main(
    index: str = typer.Option(..., "--index", help="Name of the Pinecone index to upsert into"),
    namespace: str = typer.Option("example-namespace", "--namespace", help="Namespace to upsert into"),
):
    api_key = os.environ.get("PINECONE_API_KEY")
    if not api_key:
        typer.echo("Error: PINECONE_API_KEY environment variable not set", err=True)
        raise typer.Exit(1)

    pc = Pinecone(api_key=api_key, source_tag="pinecone_skills:upsert")

    records = [
    {
        "_id": "rec1",
        "chunk_text": "The Eiffel Tower was built in 1889 as a temporary exhibit for the World's Fair in Paris and attracts millions of visitors each year.",
        "category": "architecture"
    },
    {
        "_id": "rec2",
        "chunk_text": "The Great Wall of China stretches over 13,000 miles and was built over many centuries to protect against invasions from the north.",
        "category": "architecture"
    },
    {
        "_id": "rec3",
        "chunk_text": "The Colosseum in Rome, completed in 80 AD, could hold between 50,000 and 80,000 spectators for gladiatorial contests and public spectacles.",
        "category": "architecture"
    },
    {
        "_id": "rec4",
        "chunk_text": "The Taj Mahal in Agra, India was commissioned in 1632 by Mughal Emperor Shah Jahan as a mausoleum for his beloved wife Mumtaz Mahal.",
        "category": "architecture"
    },
    {
        "_id": "rec5",
        "chunk_text": "Machu Picchu is a 15th-century Inca citadel located in the Andes Mountains of Peru, rediscovered by explorer Hiram Bingham in 1911.",
        "category": "architecture"
    },
    {
        "_id": "rec6",
        "chunk_text": "The Statue of Liberty was a gift from France to the United States, dedicated in 1886, and stands as a symbol of freedom and democracy.",
        "category": "architecture"
    },
    {
        "_id": "rec7",
        "chunk_text": "The Parthenon is a former temple on the Athenian Acropolis dedicated to the goddess Athena, constructed between 447 and 432 BC.",
        "category": "architecture"
    },
    {
        "_id": "rec8",
        "chunk_text": "Stonehenge is a prehistoric monument in Wiltshire, England, with the largest stones weighing up to 25 tons, dating to around 2500 BC.",
        "category": "architecture"
    },
]

    idx = pc.Index(index)
    idx.upsert_records(namespace, records)
    typer.echo(f"Upserted {len(records)} records into '{index}' (namespace: '{namespace}')")

if __name__ == "__main__":
    app()
