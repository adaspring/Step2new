import os
import json
import deepl
import argparse
from pathlib import Path


def create_efficient_translatable_map(
       json_data, translator, target_lang="FR", 
       primary_lang=None, secondary_lang=None,  # Add these
       memory_file=None
   ):
   """
    Efficiently create a translatable map from JSON data containing blocks of text.
    Uses batching and translation memory for optimization.
    
    Args:
        json_data: Parsed JSON data with blocks of text
        translator: DeepL translator instance
        target_lang: Target language code (default "FR")
        primary_lang: Primary source language code (from step1)
        secondary_lang: Secondary source language code (from step1)
        memory_file: Path to translation memory file
    """
    # Load translation memory if available
    translation_memory = {}
    if memory_file and os.path.exists(memory_file):
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                translation_memory = json.load(f)
            print(f"Loaded {len(translation_memory)} entries from translation memory")
        except json.JSONDecodeError:
            print(f"Warning: Could not parse translation memory file {memory_file}")
    
    # Prepare for translation
    translatable_map = {}
    texts_to_translate = []
    token_indices = {}  # Maps index to token
    original_texts = {}  # Maps token to original text for memory
    
    # Process blocks
    for block_id, block_data in json_data.items():
        # Handle main text
        if "text" in block_data:
            text = block_data["text"]
            token = block_id
            
            # Check if we already have this translation in memory
            if text in translation_memory:
                translatable_map[token] = translation_memory[text]
                print(f"Using cached translation for {token}")
            else:
                # Add to batch for translation
                index = len(texts_to_translate)
                texts_to_translate.append(text)
                token_indices[index] = token
                original_texts[token] = text  # Store original for memory
        
        # Handle segments if present
        if "segments" in block_data:
            for segment_id, segment_text in block_data["segments"].items():
                token = f"{block_id}_{segment_id}"
                
                # Check if we already have this translation in memory
                if segment_text in translation_memory:
                    translatable_map[token] = translation_memory[segment_text]
                    print(f"Using cached translation for {token}")
                else:
                    # Add to batch for translation
                    index = len(texts_to_translate)
                    texts_to_translate.append(segment_text)
                    token_indices[index] = token
                    original_texts[token] = segment_text  # Store original for memory
    
    # Batch translate if we have any new text
    if texts_to_translate:
        print(f"Translating {len(texts_to_translate)} new text segments...")
        
    batch_size = 50  # Reduced for detection overhead
    for i in range(0, len(texts_to_translate), batch_size):
        batch = texts_to_translate[i:i+batch_size]
        translated_batch = []
        
        for text in batch:
            # Phase 1: Quick detection (first 100 chars)
            try:
                sample = text[:100]  # Detection sample
                detection = translator.translate_text(
                    sample,
                    target_lang=target_lang,
                    split_sentences="none",
                    preserve_formatting=True
                )
                
                # Phase 2: Validate language
                detected_lang = detection.detected_source_lang.lower()
                allowed_langs = {
                    lang.lower() for lang in [primary_lang, secondary_lang] if lang
                }
                
                if detected_lang in allowed_langs:
                    # Phase 3: Full translation
                    result = translator.translate_text(
                        text,
                        target_lang=target_lang
                    )
                    translated_batch.append(result.text)
                else:
                    translated_batch.append(text)  # Keep original
                    
            except Exception as e:
                print(f"Language detection failed for text, keeping original: {e}")
                translated_batch.append(text)
        
        # Store results for this batch
        for j in range(len(batch)):
            index = i + j
            token = token_indices[index]
            original_text = original_texts[token]
            final_text = translated_batch[j]
            
            translatable_map[token] = final_text
            translation_memory[original_text] = final_text
        
        print(f"Processed batch {i//batch_size + 1}/{(len(texts_to_translate) + batch_size - 1)//batch_size}")
    # Save updated memory
    if memory_file and translation_memory:
        memory_dir = os.path.dirname(memory_file)
        if memory_dir and not os.path.exists(memory_dir):
            os.makedirs(memory_dir)
            
        with open(memory_file, "w", encoding="utf-8") as f:
            json.dump(translation_memory, f, ensure_ascii=False, indent=2)
        print(f"Updated translation memory with {len(translation_memory)} entries")
    
    return translatable_map

def translate_json_file(input_file, output_file, target_lang="FR", primary_lang=None, secondary_lang=None, memory_dir="translation_memory"):
    """
    Main function to translate a JSON file while maintaining the original structure.
    """
    auth_key = os.getenv("DEEPL_AUTH_KEY")
    if not auth_key:
        raise ValueError("DEEPL_AUTH_KEY environment variable not set")
    
    translator = deepl.Translator(auth_key)
    memory_file = os.path.join(memory_dir, f"translation_memory_{target_lang.lower()}.json")
    
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            json_data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Error parsing input file {input_file}: {e}")
    
    translatable_map = create_efficient_translatable_map(
        json_data, 
        translator, 
        target_lang=target_lang,
        primary_lang=primary_lang,
        secondary_lang=secondary_lang,
        memory_file=memory_file
    )
    
    # Create translated structure
    translated_data = {}
    for block_id, block_data in json_data.items():
        translated_block = block_data.copy()
        
        if "text" in block_data:
            translated_block["text"] = translatable_map.get(block_id, block_data["text"])
        
        if "segments" in block_data:
            translated_segments = {}
            for segment_id, segment_text in block_data["segments"].items():
                token = f"{block_id}_{segment_id}"
                translated_segments[segment_id] = translatable_map.get(token, segment_text)
            translated_block["segments"] = translated_segments
        
        translated_data[block_id] = translated_block
    
    # Save output
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(translated_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Translation completed: {output_file} with {len(translatable_map)} entries")
    return translated_data

def main():
    parser = argparse.ArgumentParser(description="Translate JSON content using DeepL")
    parser.add_argument("--input", "-i", default="translatable_flat.json", help="Input JSON file")
    parser.add_argument("--output", "-o", default="translations.json", help="Output JSON file")
    parser.add_argument("--lang", "-l", required=True, help="Target language code (e.g., FR, ES)")
    parser.add_argument("--primary-lang", help="Primary source language (from step1_extract.py --lang)")
    parser.add_argument("--secondary-lang", help="Secondary language (from step1_extract.py --secondary-lang)")
    parser.add_argument("--memory", "-m", default="translation_memory", help="Translation memory directory")
    parser.add_argument("--apply", "-a", action="store_true", help="Apply translations to original structure")
    args = parser.parse_args()
    
    try:
        translations = translate_json_file(
            args.input,
            args.output,
            target_lang=args.lang,
            primary_lang=args.primary_lang,
            secondary_lang=args.secondary_lang,
            memory_dir=args.memory
        )
        
        if args.apply:
            apply_translations(args.input, args.output, f"translated_{args.input}")
            
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
