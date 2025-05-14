import os
import json
import deepl
import argparse
from pathlib import Path


def create_efficient_translatable_map(json_data, translator, target_lang="FR", memory_file=None):
    """
    Efficiently create a translatable map from JSON data containing blocks of text.
    Uses batching and translation memory for optimization.
    
    Args:
        json_data: Parsed JSON data with blocks of text
        translator: DeepL translator instance
        target_lang: Target language code (default "FR")
        memory_file: Path to translation memory file
        
    Returns:
        Dictionary mapping tokens to translated text
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
        
        # Use a reasonable batch size to avoid API limits
        batch_size = 50  # Adjust based on DeepL API limits
        for i in range(0, len(texts_to_translate), batch_size):
            batch = texts_to_translate[i:i+batch_size]
            
            try:
                results = translator.translate_text(batch, target_lang=target_lang)
                
                for j, result in enumerate(results):
                    index = i + j
                    token = token_indices[index]
                    original_text = original_texts[token]
                    
                    # Save to map and memory
                    translatable_map[token] = result.text
                    translation_memory[original_text] = result.text
                    
                print(f"Translated batch {i//batch_size + 1}/{(len(texts_to_translate) + batch_size - 1)//batch_size}")
                
            except Exception as e:
                print(f"Error translating batch starting at index {i}: {e}")
                # Continue with the next batch
    
    # Save updated memory if we have a file path
    if memory_file and translation_memory:
        memory_dir = os.path.dirname(memory_file)
        if memory_dir and not os.path.exists(memory_dir):
            os.makedirs(memory_dir)
            
        with open(memory_file, "w", encoding="utf-8") as f:
            json.dump(translation_memory, f, ensure_ascii=False, indent=2)
        print(f"Updated translation memory with {len(translation_memory)} entries")
    
    return translatable_map


def translate_json_file(input_file, output_file, target_lang="FR", memory_dir="translation_memory"):
    """
    Main function to translate a JSON file.
    
    Args:
        input_file: Path to input JSON file
        output_file: Path to output JSON file for translations
        target_lang: Target language code (default "FR")
        memory_dir: Directory to store translation memory files
    """
    # Ensure the auth key is available
    auth_key = os.getenv("DEEPL_AUTH_KEY")
    if not auth_key:
        raise ValueError("DEEPL_AUTH_KEY environment variable not set. Please set it before running.")
    
    # Create translator instance
    translator = deepl.Translator(auth_key)
    
    # Memory file path
    memory_file = os.path.join(memory_dir, f"translation_memory_{target_lang.lower()}.json")
    
    # Load input data
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            json_data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Error parsing input file {input_file}: {e}")
    
    # Create translatable map
    translatable_map = create_efficient_translatable_map(
        json_data, 
        translator, 
        target_lang=target_lang, 
        memory_file=memory_file
    )
    
    # Save the output
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(translatable_map, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Translation completed: {output_file} with {len(translatable_map)} entries")
    
    return translatable_map


def apply_translations(original_file, translations_file, output_file):
    """
    Apply translations to the original JSON structure.
    
    Args:
        original_file: Path to original JSON file
        translations_file: Path to translations JSON file
        output_file: Path to output translated JSON file
    """
    # Load files
    with open(original_file, "r", encoding="utf-8") as f:
        original_data = json.load(f)
    
    with open(translations_file, "r", encoding="utf-8") as f:
        translations = json.load(f)
    
    # Create a new structure with translations
    translated_data = {}
    
    for block_id, block_data in original_data.items():
        # Create a new block
        translated_block = block_data.copy()
        
        # Replace the text if we have a translation
        if "text" in block_data and block_id in translations:
            translated_block["text"] = translations[block_id]
        
        # Replace segments if we have translations
        if "segments" in block_data:
            translated_segments = {}
            for segment_id, segment_text in block_data["segments"].items():
                token = f"{block_id}_{segment_id}"
                if token in translations:
                    translated_segments[segment_id] = translations[token]
                else:
                    translated_segments[segment_id] = segment_text  # Keep original if no translation
            
            translated_block["segments"] = translated_segments
        
        translated_data[block_id] = translated_block
    
    # Save the translated structure
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(translated_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Applied translations: {output_file}")


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Efficiently translate JSON content using DeepL API")
    parser.add_argument("--input", "-i", default="translatable_flat.json", help="Input JSON file path")
    parser.add_argument("--output", "-o", default="translations.json", help="Output JSON file path")
    parser.add_argument("--lang", "-l", default="FR", help="Target language code (e.g., FR, ES, DE)")
    parser.add_argument("--memory", "-m", default="translation_memory", help="Directory for translation memory files")
    parser.add_argument("--apply", "-a", action="store_true", help="Apply translations to original structure")
    args = parser.parse_args()
    
    try:
        # First translate the content
        translations = translate_json_file(args.input, args.output, args.lang, args.memory)
        
        # If --apply flag is set, apply translations to original structure
        if args.apply:
            apply_translations(args.input, args.output, f"translated_{args.input}")
            
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    # If running as script, execute main function
    exit_code = main()
    exit(exit_code)
