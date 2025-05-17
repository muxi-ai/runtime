# Tutorial: Fine-tune Mistral 7B and run it with llama.cpp (and Ollama)

This tutorial provides a step-by-step guide to fine-tuning the **Mistral 7B** model for task decomposition (or similar agent orchestration tasks), converting it to GGUF format, and running it locally using `llama.cpp`. An appendix explains how to convert and package the model for Ollama.

> [!NOTE]
> We chose **Mistral 7B** for its excellent performance, open Apache 2.0 license, and broad compatibility with tooling like `llama.cpp` and Ollama. Its permissive licensing ensures we can fine-tune, bundle, and redistribute the model freely — making it an ideal choice for powering agent orchestration inside MUXI.

---

## Prerequisites

### Hardware:

* Linux/macOS/Windows machine with **24–32 GB RAM** and **16 GB+ GPU** (for fine-tuning)
* For inference only: 8–12 GB VRAM (with quantized GGUF model)

### Software:

* Python 3.10+
* Git
* Conda (recommended)

### Python dependencies:

```bash
pip install torch transformers datasets peft accelerate bitsandbytes scipy
```

---

## System Requirements for Inference (Post Fine-Tuning)

Once you've fine-tuned and converted the model to GGUF format, you can run it efficiently on the following setups:

### Minimum VPS/Container Specs (for quantized model):

| Component          | Recommended   | Notes                                               |
| ------------------ | ------------- | --------------------------------------------------- |
| **RAM**            | 8–16 GB       | Depending on quantization level (q4\_K\_M vs q5\_1) |
| **CPU**            | 4–8 vCPUs     | Works well with `llama.cpp` on CPU only             |
| **GPU (optional)** | 8–12 GB VRAM  | For better response time in `llama.cpp` or Ollama   |
| **Storage**        | \~8 GB        | For storing GGUF model + Ollama cache               |
| **OS**             | Ubuntu 22.04+ | Or macOS (M1/M2 supported natively)                 |

### Example:

* A VPS with **4 vCPUs + 16 GB RAM** can run `llama.cpp` or Ollama with a q5\_1 GGUF model smoothly
* For M1/M2 MacBooks: expect **10–25 tokens/sec** with Metal acceleration enabled

If you're embedding this in a Docker container, ensure memory limits are appropriate and swap space is available if needed.

---

## Step 1: Download the base Mistral 7B model

```bash
from huggingface_hub import snapshot_download

snapshot_download(repo_id="mistralai/Mistral-7B-Instruct-v0.1", local_dir="mistral-base", local_dir_use_symlinks=False)
```

---

## Step 2: Prepare your fine-tuning dataset

Use the Alpaca-style instruction format:

```json
{
  "instruction": "Write an article about butterflies.",
  "input": "",
  "output": "1. Research butterflies.\n2. Create outline.\n3. Write article.\n4. Proofread."
}
```

Save as `decompose_data.json`, then load with:

```python
from datasets import load_dataset

dataset = load_dataset("json", data_files="decompose_data.json")
```

---

## Step 3: Load Mistral with 4-bit QLoRA setup

```python
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import get_peft_model, LoraConfig, TaskType

tokenizer = AutoTokenizer.from_pretrained("mistral-base", use_fast=True)
model = AutoModelForCausalLM.from_pretrained(
    "mistral-base",
    load_in_4bit=True,
    device_map="auto"
)

lora_config = LoraConfig(
    r=8,
    lora_alpha=16,
    lora_dropout=0.1,
    bias="none",
    task_type=TaskType.CAUSAL_LM
)

model = get_peft_model(model, lora_config)
```

---

## Step 4: Format dataset for training

```python
from transformers import DataCollatorForSeq2Seq

def format(example):
    prompt = f"### Instruction:\n{example['instruction']}\n\n### Response:\n{example['output']}"
    return tokenizer(prompt, truncation=True, padding="max_length", max_length=512)

dataset = dataset["train"].map(format)
data_collator = DataCollatorForSeq2Seq(tokenizer, padding=True)
```

---

## Step 5: Fine-tune with `Trainer`

```python
from transformers import Trainer, TrainingArguments

training_args = TrainingArguments(
    output_dir="./mistral-finetuned",
    per_device_train_batch_size=2,
    gradient_accumulation_steps=4,
    num_train_epochs=3,
    logging_steps=10,
    save_strategy="epoch",
    fp16=True,
    bf16=False
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
    data_collator=data_collator
)

trainer.train()
```

---

## Step 6: Merge LoRA weights

```python
from peft import PeftModel
from transformers import AutoModelForCausalLM

base_model = AutoModelForCausalLM.from_pretrained("mistral-base")
peft_model = PeftModel.from_pretrained(base_model, "mistral-finetuned")
peft_model = peft_model.merge_and_unload()
peft_model.save_pretrained("mistral-merged")
tokenizer.save_pretrained("mistral-merged")
```

---

## Step 7: Convert to GGUF for `llama.cpp`

Install the converter:

```bash
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
pip install -r requirements.txt
```

Convert the model:

```bash
python convert.py --outfile ./mistral.gguf --model_dir ./mistral-merged
```

Move the `.gguf` file into `llama.cpp/models` and run:

```bash
./main -m models/mistral.gguf -p "Break down the task: Write a blog post about climate change"
```

---

# Appendix A: Ollama integration

## Step A1: Create a `Modelfile`

```Dockerfile
FROM mistral
PARAMETER stop "<|endoftext|>"
PARAMETER temperature 0.7
PARAMETER top_k 50
PARAMETER top_p 0.95
PARAMETER num_ctx 2048

WEIGHTS ./mistral.gguf
```

## Step A2: Build the Ollama model

```bash
ollama create mistral-decomposer -f Modelfile
```

## Step A3: Run in Ollama

```bash
ollama run mistral-decomposer
```

## Step A4: Call from Python

```python
import requests

res = requests.post("http://localhost:11434/api/generate", json={
    "model": "mistral-decomposer",
    "prompt": "Break down the task: Write an article about climate change",
    "stream": False
})

print(res.json()['response'])
```

---


# Appendix B: Understanding Quantization Levels

Quantization reduces model size and memory usage by storing weights with lower precision (e.g., 4-bit or 5-bit integers instead of full floats). GGUF models come in several quantization formats.

## Common GGUF Quantization Types

| Quant Level  | Size        | VRAM Required | Accuracy       | Speed      | Notes                                        |
| ------------ | ----------- | ------------- | -------------- | ---------- | -------------------------------------------- |
| **q4\_0**    | Smallest    | \~5 GB        | 🔴 Low         | 🟢 Fastest | Basic 4-bit — lower accuracy                 |
| **q4\_K\_M** | ⚖️ Balanced | \~6.5–7 GB    | 🟡 Good        | 🟢 Fast    | Popular trade-off for size + performance     |
| **q5\_0**    | Medium      | \~7.5–8 GB    | 🟡 Good+       | 🟡 Medium  | Better precision with modest size            |
| **q5\_1**    | Larger      | \~8.5–9 GB    | 🟢 Very good   | 🟡 Medium  | Best balance for accuracy and resource usage |
| **q6\_K**    | Large       | \~10 GB       | 🟢 Excellent   | 🔴 Slower  | High fidelity for sensitive tasks            |
| **F16**      | Full        | \~13–16 GB    | 🟢🟢 Excellent | 🔴 Slowest | Unquantized, for testing only                |

## Recommended Strategy

* Include multiple quantized GGUF models in your Docker image (e.g., `q4_K_M`, `q5_1`, `q6_K`)
* Allow users to select the model variant based on available system memory and accuracy needs

**Suggested defaults:**

* `q4_K_M` = fallback for minimal setups
* `q5_1` = default for balanced deployments
* `q6_K` = optional for high-accuracy use cases


---

# Done ✅

You now have:

* A fine-tuned Mistral 7B model
* Converted to GGUF format
* Ready for local use via `llama.cpp` or Ollama
