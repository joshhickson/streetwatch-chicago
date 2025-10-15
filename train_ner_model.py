#!/usr/bin/env python3
"""
Script to train a custom spaCy NER model for Chicago location extraction.
"""
import json
import spacy
from spacy.tokens import DocBin
from spacy.training import Example
from pathlib import Path
import random

# Configuration
TRAINING_DATA_PATH = Path("data/training_data.jsonl")
OUTPUT_MODEL_PATH = Path("models/custom_ner_model")
BASE_MODEL = "en_core_web_sm"
N_ITER = 30
CUSTOM_LABEL = "CHI_LOCATION"

def load_training_data(filepath):
    """Load training data from JSONL file."""
    training_data = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            item = json.loads(line.strip())
            text = item['text']
            entities = [(span['start'], span['end'], span['label']) for span in item['spans']]
            training_data.append((text, {"entities": entities}))
    return training_data

def create_training_examples(nlp, training_data):
    """Convert training data to spaCy Example objects."""
    examples = []
    for text, annotations in training_data:
        doc = nlp.make_doc(text)
        example = Example.from_dict(doc, annotations)
        examples.append(example)
    return examples

def train_ner_model():
    """Train a custom NER model."""
    print(f"Loading base model: {BASE_MODEL}")
    nlp = spacy.load(BASE_MODEL)
    
    # Get or create NER component
    if "ner" not in nlp.pipe_names:
        ner = nlp.add_pipe("ner")
        print("Added NER component to pipeline")
    else:
        ner = nlp.get_pipe("ner")
        print("Using existing NER component")
    
    # Add custom label
    ner.add_label(CUSTOM_LABEL)
    print(f"Added custom label: {CUSTOM_LABEL}")
    
    # Load training data
    print(f"Loading training data from: {TRAINING_DATA_PATH}")
    training_data = load_training_data(TRAINING_DATA_PATH)
    print(f"Loaded {len(training_data)} training examples")
    
    # Create training examples
    examples = create_training_examples(nlp, training_data)
    
    # Get names of other pipes to disable during training
    other_pipes = [pipe for pipe in nlp.pipe_names if pipe != "ner"]
    
    # Train the model
    print(f"\nTraining model for {N_ITER} iterations...")
    with nlp.disable_pipes(*other_pipes):
        optimizer = nlp.resume_training()
        
        for iteration in range(N_ITER):
            random.shuffle(examples)
            losses = {}
            
            # Batch training examples
            for batch in spacy.util.minibatch(examples, size=2):
                nlp.update(batch, drop=0.5, losses=losses, sgd=optimizer)
            
            if (iteration + 1) % 5 == 0:
                print(f"Iteration {iteration + 1}/{N_ITER} - Loss: {losses.get('ner', 0):.4f}")
    
    # Save the model
    print(f"\nSaving model to: {OUTPUT_MODEL_PATH}")
    OUTPUT_MODEL_PATH.mkdir(parents=True, exist_ok=True)
    nlp.to_disk(OUTPUT_MODEL_PATH)
    
    # Verify the model
    print("\n✅ Model training complete!")
    print(f"Labels in trained model: {ner.labels}")
    
    # Test the model
    print("\nTesting model on sample text...")
    test_text = "ICE agents were seen at 75th Street and South Shore Drive in Chicago."
    doc = nlp(test_text)
    print(f"Input: {test_text}")
    print(f"Entities found: {[(ent.text, ent.label_) for ent in doc.ents]}")

if __name__ == "__main__":
    train_ner_model()
