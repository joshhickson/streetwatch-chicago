import spacy
from spacy.tokens import DocBin
from spacy.training import Example
import json
from pathlib import Path
import sys
import random
from src.logger import log

# --- Configuration ---
BASE_DIR = Path(__file__).resolve().parent.parent
TRAINING_DATA_PATH = BASE_DIR / "data" / "training_data.jsonl"
MODEL_OUTPUT_PATH = BASE_DIR / "models" / "custom_ner_model"
ITERATIONS = 30

def load_training_data(path: Path):
    """Loads training data from a JSONL file."""
    log.info(f"Loading training data from {path}")
    if not path.exists() or path.stat().st_size == 0:
        log.error("Training data file not found or is empty.")
        sys.exit(1)

    training_data = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line)
                text = data['text']
                annotations = {"entities": [(span['start'], span['end'], span['label']) for span in data.get("spans", [])]}
                training_data.append((text, annotations))
            except json.JSONDecodeError:
                log.error(f"Error decoding JSON in line: {line.strip()}")
            except KeyError as e:
                log.error(f"Missing key {e} in line: {line.strip()}")

    log.info(f"Successfully loaded {len(training_data)} training examples.")
    return training_data

def train_ner_model(training_data):
    """Trains a custom NER model using a programmatic training loop."""
    log.info("--- Starting programmatic model training ---")

    # 1. Create a blank spaCy model
    nlp = spacy.blank("en")
    log.info("Created blank 'en' model.")

    # 2. Create and configure the NER pipeline component
    if "ner" not in nlp.pipe_names:
        ner = nlp.add_pipe("ner", last=True)
        log.info("Added 'ner' component to the pipeline.")
    else:
        ner = nlp.get_pipe("ner")

    # 3. Add all unique entity labels to the NER component
    for _, annotations in training_data:
        for ent in annotations.get("entities"):
            ner.add_label(ent[2])

    log.info(f"Added labels to NER component: {ner.labels}")

    # 4. Convert training data to spaCy's Example objects
    examples = []
    for text, annotations in training_data:
        try:
            doc = nlp.make_doc(text)
            examples.append(Example.from_dict(doc, annotations))
        except Exception as e:
            log.error(f"Error creating example for text: '{text}'. Error: {e}")
            continue

    # 5. Disable other pipes and begin the training loop
    other_pipes = [pipe for pipe in nlp.pipe_names if pipe != "ner"]
    with nlp.disable_pipes(*other_pipes):
        optimizer = nlp.begin_training()
        log.info("Starting training loop...")
        for itn in range(ITERATIONS):
            random.shuffle(examples)
            losses = {}
            for batch in spacy.util.minibatch(examples, size=8):
                try:
                    nlp.update(batch, drop=0.35, losses=losses, sgd=optimizer)
                except Exception as e:
                    log.error(f"Error during training update: {e}")
                    # Log the problematic texts for debugging
                    for ex in batch:
                        log.error(f"Problematic text: {ex.text}")
                    continue

            if (itn + 1) % 5 == 0:
                log.info(f"Iteration {itn + 1}/{ITERATIONS} - Losses: {losses}")

    # 6. Save the trained model to disk
    log.info("--- Training complete ---")
    if MODEL_OUTPUT_PATH.exists():
        import shutil
        shutil.rmtree(MODEL_OUTPUT_PATH)
        log.info(f"Removed existing model directory at {MODEL_OUTPUT_PATH}")

    MODEL_OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    nlp.to_disk(MODEL_OUTPUT_PATH)
    log.info(f"Successfully saved trained model to {MODEL_OUTPUT_PATH}")

if __name__ == "__main__":
    log.info("Starting custom NER model training pipeline.")
    data = load_training_data(TRAINING_DATA_PATH)
    if data:
        train_ner_model(data)
    else:
        log.critical("No valid training data was loaded. Aborting training.")
    log.info("NER model training pipeline finished.")