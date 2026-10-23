# Colab fine-tuning lane (optional)

This directory documents an optional experiment. Fine-tuning is not required to prove the core product.

Before training:
1. Confirm the exact model repository ID, license/access, and Transformers architecture support.
2. Prepare a clean JSONL dataset of diagnostics + original code + desired unified diff.
3. Split train/validation data and keep an untouched evaluation set.
4. Run a tiny forward pass before training.
5. Confirm the GPU can load the selected model and context length; do not assume a free T4 will fit.
6. Evaluate the fine-tuned model against a baseline on patch validity, regression rate, and requirement preservation.
7. Confirm the exported artifact format is supported by the intended inference server.

The original proposed notebook was a placeholder with `dataset = None`, so it could not train as-is. The actual notebook should be created only after model and library compatibility are verified.
