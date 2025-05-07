# Tutorial: Fine-tune Phi-3 Mini and run it with llama.cpp (and Ollama)

This tutorial provides a full step-by-step guide to fine-tuning the **Phi-3 Mini (3.8B)** model for task decomposition, converting it to GGUF format, and running it locally using `llama.cpp`. An appendix explains how to convert and package the model for Ollama.

---

## Prerequisites

### Hardware:

* Apple Silicon (M1/M2) or any Linux/Windows machine with \~16 GB RAM (GPU not required, but helpful)

### Software:

* Python 3.10+
* Git
* Conda (recommended)

### Python dependencies:

```bash
pip install torch transformers datasets peft accelerate bitsandbytes scipy
```

---

## Step 1: Download the base Phi-3 Mini model

```bash
from huggingface_hub import snapshot_download

snapshot_download(repo_id="microsoft/Phi-3-mini-128k-instruct", local_dir="phi3-base", local_dir_use_symlinks=False)
```

---

## Step 2: Prepare your fine-tuning dataset

Use the Alpaca format:

```json
{
  "instruction": "Write an article about butterflies.",
  "input": "",
  "output": "1. Research butterflies.\n2. Create outline.\n3. Write article.\n4. Proofread."
}
```

Save your dataset as `decompose_data.json`.

Load it with:

```python
from datasets import load_dataset

dataset = load_dataset("json", data_files="decompose_data.json")
```

---

## Step 3: Load Phi-3 with 4-bit QLoRA setup

```python
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import get_peft_model, LoraConfig, TaskType

model_name = "phi3-base"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(
    model_name,
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
    output_dir="./phi3-finetuned",
    per_device_train_batch_size=2,
    gradient_accumulation_steps=4,
    num_train_epochs=3,
    logging_steps=10,
    save_strategy="epoch",
    fp16=False,
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

base_model = AutoModelForCausalLM.from_pretrained("phi3-base")
peft_model = PeftModel.from_pretrained(base_model, "phi3-finetuned")
peft_model = peft_model.merge_and_unload()
peft_model.save_pretrained("phi3-merged")
tokenizer.save_pretrained("phi3-merged")
```

---

## Step 7: Convert to GGUF for `llama.cpp`

Install the converter:

```bash
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
pip install -r requirements.txt
```

Run the conversion:

```bash
python convert.py --outfile ./phi3.gguf --model_dir ./phi3-merged
```

Move the `.gguf` file into `llama.cpp/models`.

Run the model:

```bash
./main -m models/phi3.gguf -p "Break down the task: Write a blog post about climate change"
```

---

# Appendix: Ollama integration

## Step A1: Create a `Modelfile`

```Dockerfile
FROM llama3
PARAMETER stop "<|endoftext|>"
PARAMETER temperature 0.7
PARAMETER top_k 50
PARAMETER top_p 0.95
PARAMETER num_ctx 2048

WEIGHTS ./phi3.gguf
```

## Step A2: Build the Ollama model

```bash
ollama create phi3-decomposer -f Modelfile
```

## Step A3: Run in Ollama

```bash
ollama run phi3-decomposer
```

## Step A4: Call from Python

```python
import requests

res = requests.post("http://localhost:11434/api/generate", json={
    "model": "phi3-decomposer",
    "prompt": "Break down the task: Write an article about climate change",
    "stream": False
})

print(res.json()['response'])
```

---

# Done ✅

You now have:

* A fine-tuned Phi-3 Mini model
* Converted to GGUF
* Ready for local use via `llama.cpp` or Ollama
