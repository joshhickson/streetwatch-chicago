# Known Issues and Limitations

## Custom NER Model Training Issue

**Status:** Identified  
**Severity:** Medium  
**Impact:** Custom CHI_LOCATION labels not extracting; system falls back to base model

### Problem Description

The custom NER model (`models/custom_ner_model`) was successfully trained with the `CHI_LOCATION` label, but suffers from two critical issues:

1. **Entity Alignment Errors**: All 14 training examples have misaligned entity spans that don't match spaCy's token boundaries. This causes warnings during training:
   ```
   [W030] Some entities could not be aligned in the text...
   ```

2. **Catastrophic Forgetting**: Training only on `CHI_LOCATION` examples caused the model to lose its ability to recognize standard labels (GPE, LOC, ORG, PERSON, etc.) that were present in the base `en_core_web_sm` model.

### Current Behavior

- Custom model loads successfully
- `CHI_LOCATION` label is present in model
- Model extracts **0 locations** from test inputs
- System gracefully falls back to base model's GPE/LOC extraction
- All core functionality (temporal extraction, geocoding, deduplication) works correctly

### Root Cause

The training data in `data/training_data.jsonl` has entity spans that include surrounding context or don't align with tokenization. For example:

```json
{"text": "ICE checkpoint near 75th Street and South Shore Drive", "spans": [{"start": 21, "end": 56, "label": "CHI_LOCATION"}]}
```

The span "75th Street and South Shore Drive" might not align with spaCy's tokens after preprocessing, causing the training to fail to learn proper boundaries.

### Workaround

The system currently operates with the base `en_core_web_sm` model, which successfully extracts:
- **GPE** labels: Cities, states, countries ("Chicago", "Illinois")
- **LOC** labels: Non-GPE locations, geographic features
- Standard NER entities work as expected

### Solution (Future Work)

To fix the custom NER model:

1. **Re-annotate Training Data** with clean entity boundaries:
   - Ensure spans align with token boundaries
   - Remove surrounding context words ("near", "at", etc.) from entity spans
   - Use spaCy's `offsets_to_biluo_tags` to validate alignments before training

2. **Prevent Catastrophic Forgetting** using one of these approaches:
   - **Option A**: Include examples of standard entities (GPE, LOC, etc.) in training data
   - **Option B**: Use spaCy's `rehearsal` technique to retain base model knowledge
   - **Option C**: Fine-tune only the new label without updating existing entity weights

3. **Increase Training Data**: 14 examples is minimal; aim for 100+ diverse examples

### Testing Evidence

```bash
# With custom model (broken):
curl -X POST /process-sighting -d '{"post_text": "ICE in Chicago"}'
→ Extracted 0 locations

# With base model (working):
curl -X POST /process-sighting -d '{"post_text": "ICE in Chicago"}'
→ Extracted 1 location: "Chicago" (GPE)
→ Successfully geocoded and stored
```

### Impact Assessment

**Currently:** ✅ System is fully operational
- Temporal extraction: Working
- Context-aware geocoding: Working
- Deduplication: Working
- Location extraction: Working (via base model GPE/LOC)

**Missing:** Chicago-specific location extraction
- Cannot extract intersections ("Fullerton and Western")
- Cannot recognize neighborhood names ("Logan Square", "Humboldt Park")
- Cannot identify local landmarks ("Rico Fresh supermarket")

### Recommendation

For production use:
1. **Short-term**: Continue using base model (current state) - fully functional
2. **Medium-term**: Re-annotate training data with proper boundaries
3. **Long-term**: Consider BERT-based NER (more robust) as recommended in Oct 7 analysis
