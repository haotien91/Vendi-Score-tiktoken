import sys
import os
import json

# 將 Vendi-Score 目錄添加到 Python 路徑中
vendi_score_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Vendi-Score'))
sys.path.append(vendi_score_path)

# 現在我們可以引入 vendi_score 包中的模塊
from vendi_score import vendi
from vendi_score import text_utils

def read_jsonl(file_path):
    prompts = []
    outputs = []
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            data = json.loads(line)
            prompts.append(data['messages'][1]['content'])
            outputs.append(data['messages'][2]['content'])
    return prompts, outputs

def calculate_vendi(texts):
    return text_utils.tiktoken_vendi_score(texts)

def main():
    jsonl_path = 'example/nstc_od_簽_finetune_format_charlessnp_train.jsonl'
    prompts, outputs = read_jsonl(jsonl_path)

    vendi_prompts = calculate_vendi(prompts)
    vendi_outputs = calculate_vendi(outputs)

    print(f"Vendi score for prompts: {vendi_prompts:.02f}")
    print(f"Vendi score for outputs: {vendi_outputs:.02f}")

if __name__ == "__main__":
    main()
