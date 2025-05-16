import os
import sys
import json
import uuid
import spacy
import argparse
import subprocess
import regex as re
from pypinyin import lazy_pinyin
from bs4 import BeautifulSoup, Comment, NavigableString

# Language models for spaCy
SPACY_MODELS = {
    "en": "en_core_web_sm",
    "zh": "zh_core_web_sm",
    "fr": "fr_core_news_sm",
    "es": "es_core_news_sm",
    "de": "de_core_news_sm",
    "it": "it_core_news_sm",
    "pt": "pt_core_news_sm",
    "ru": "ru_core_news_sm",
    "el": "el_core_news_sm",
    "ja": "ja_core_news_sm",
    "ko": "ko_core_news_sm",
    "nl": "nl_core_news_sm",
    "pl": "pl_core_news_sm",
    "ar": "ar_core_news_sm",
    "xx": "xx_ent_wiki_sm"
}

TRANSLATABLE_TAGS = {
    "p", "span", "div", "h1", "h2", "h3", "h4", "h5", "h6",
    "label", "button", "li", "td", "th", "a", "strong", "em",
    "b", "i", "caption", "summary", "figcaption", "option", "optgroup",
    "legend", "mark", "output", "details", "time", "abbr", "address", "article",
    "aside", "bdi", "bdo", "blockquote", "cite", "data", "dd", "dfn", "dl", "dt",
    "fieldset", "footer", "header", "ins", "kbd", "main", "nav", "q", "rp", "rt",
    "ruby", "s", "samp", "section", "small", "sub", "sup", "u", "var", "textarea",
    "meter", "progress", "audio", "track", "video", "custom-element", "x-component"
}

TRANSLATABLE_ATTRS = {
    "alt", "title", "placeholder", "aria-label", "aria-placeholder", "aria-valuetext",
    "aria-roledescription", "value", "data-i18n", "data-caption", "data-title",
    "data-tooltip", "data-label", "data-error", "aria-description", "aria-details",
    "aria-errormessage", "aria-keyshortcuts", "aria-labelledby", "data-message",
    "data-content", "data-text", "data-description", "data-alt", "data-prompt",
    "data-hint", "data-warning", "data-success-message", "data-error-message",
    "data-empty-message", "data-confirmation", "data-fallback-text",
    "data-notification", "v-tooltip", "ng-attr-title", "x-tooltip", "react-tooltip",
    "tooltip-content", "tooltip-text", "ng-placeholder", "v-placeholder",
    "pattern-description", "validation-message", "help-text", "description-text"
}

SEO_META_FIELDS = {
    "name": {
        "description", "keywords", "robots", "author", "viewport", "theme-color",
        "application-name", "twitter:label1", "twitter:data1", "twitter:label2",
        "twitter:data2", "news_keywords", "summary", "abstract", "subject",
        "topic", "copyright", "language", "designer", "generator", "owner"
    },
    "property": {
        "og:title", "og:description", "og:image", "og:url", "twitter:title",
        "twitter:description", "twitter:image", "twitter:card", "og:site_name",
        "og:locale", "product:brand", "article:author", "article:section",
        "article:tag", "book:author", "music:creator", "place:location:latitude",
        "video:director", "profile:username", "product:availability",
        "og:video:tag"
    },
    "itemprop": {
        "name", "description", "headline", "author", "articleBody",
        "reviewBody", "recipeInstructions", "text", "caption",
        "alternativeHeadline", "award", "education", "jobTitle", "worksFor"
    }
}

TRANSLATABLE_JSONLD_KEYS = {
    # Generic
    "name", "description", "headline", "caption", "text", "title", "summary",
    "alternativeHeadline", "alternateName", "reviewBody", "articleBody",

    # Creative works & articles
    "about", "abstract", "articleSection", "comment", "backstory",

    # Education & learning
    "courseDescription", "learningResourceType",

    # Product-related
    "slogan", "disambiguatingDescription", "roleDescription", "applicationCategory",

    # Visual and media
    "contentDescription", "mainContentOfPage", "shortDescription", "genre",

    # Social or user-generated
    "author", "creator", "position", "keywords"
}

SKIP_PARENTS = {
    "script", "style", "code", "pre", "noscript", "template", "svg", "canvas",
    "frameset", "frame", "noframes", "object", "embed", "base", "map", "xmp",
    "plaintext", "math", "annotation", "datalist", "select", "option"
}

BLOCKED_ATTRS = {
    # Layout and behavior
    "accept", "align", "autocomplete", "bgcolor", "charset", "content", "dir",
    "download", "href", "id", "lang", "name", "rel", "src", "style", "type",
    "action", "method", "enctype", "target", "wrap",

    # Inputs and forms
    "pattern", "readonly", "step", "max", "min", "size", "multiple", "list",

    # Display and structure
    "colspan", "rowspan", "headers", "height", "width", "hidden", "poster",
    "preload", "media", "start",

    # Media and multimedia
    "high", "low", "kind", "srcset", "frameborder",

    # Accessibility and roles
    "role", "selected", "aria-hidden",

    # Framework-specific control (not to be translated)
    "v-if", "v-else", "v-for", "ng-if", "ng-show", "x-data", "x-show"
}

JSONLD_EXCLUDE_KEYS = {
    "duration", "uploadDate", "embedUrl", "contentUrl", "thumbnailUrl", "url",
    "fileFormat", "encodingFormat", "dateCreated", "dateModified", "datePublished",
    "width", "height", "email", "telephone", "addressCountry", "postalCode",
    "addressRegion", "latitude", "longitude", "target", "identifier"
}

EXCLUDED_META_NAMES = {
    "viewport",                      # layout
    "theme-color",                   # browser color
    "msapplication-TileColor",      # Windows live tile
    "apple-mobile-web-app-capable", # iOS fullscreen
    "apple-touch-icon",             # iOS icons
    "mobile-web-app-capable",       # Android fullscreen
    "application-name"              # PWA app name
}

EXCLUDED_META_PROPERTIES = {
    "og:url", "og:image", "og:image:width", "og:image:height", "og:locale:alternate",
    "og:video", "og:video:width", "og:video:height", "twitter:image",
    "twitter:card", "twitter:site", "twitter:creator"
}

# --- CODE PATTERNS (including JavaScript + TypeScript) ---

CODE_PATTERNS = [
    r'(\w+)\.(\w+).*?',                          # Method calls: obj.fn()
    r'(?<!\w)([A-Za-z0-9_]+)(?:\s*)=(?:\s*)',        # Assignments: const x = ...
    r'<\/?[a-z0-9-]+(?:\s+[^>]*)?\/?>',              # HTML tags
    r'{\s*[\w\s,:"\']*\s*}',                         # Object literals
    r'[^]*',                                   # Array literals
    r'(import|export|from|as)\s+[\w\s,{}*]+',        # Imports/exports
    r'console\.(log|error|warn|info)',               # Console calls
    r'function\s+\w+\s*[^)]*',                   # Function declarations
    r'@\w+(?:[^)]*)?',                           # Decorators: @Something(...)
    r'#[a-fA-F0-9]{3,8}',                            # Hex color codes
    r'\$\{[^}]*\}',                                  # Template literals: ${...}

    # TypeScript-specific additions:
    r'\b(let|const|var)\s+\w+\s*:\s*[\w<>{}, ]+', # Type annotations
    r'\binterface\s+\w+\s*{[^}]*}',                  # Interfaces
    r'\benum\s+\w+\s*{[^}]*}',                       # Enums
    r'\bfunction\s+\w+\s*<[^>]+>\s*[^)]*'        # Generics
]

# Compile combined code pattern
CODE_PATTERN_COMBINED = re.compile('|'.join(CODE_PATTERNS))

# --- TEMPLATE MARKERS ---

TEMPLATE_MARKERS = [
    r'{{[^}]*}}',                             # Mustache / Handlebars
    r'{%[^%]*%}',                             # Jinja2 / Liquid
    r'{#[^#]*#}',                             # Jinja2 comments
    r'\${[^}]*}',                             # JS/TS templates
    r'@[^)]*',                            # Angular expressions
    r'%[^)]*s',                           # Python-style formatting
    r'\s*[\w\s.]*\s*',                # Vue / Angular bindings
    r'<\?=\s*\$[\w\'\"]+\s*\?>',          # PHP short echo
    r'<\?php.*?\?>',                          # PHP full block
    r'\$\{.*?\}',                             # Shell variables
    r'\$[A-Za-z0-9_]+',                       # $VAR
    r'<#.*?#>',                               # ASP.NET Razor
    r'<\:.*?>'                                # JSP expressions
]

# Compile combined template pattern
TEMPLATE_PATTERN_COMBINED = re.compile('|'.join(TEMPLATE_MARKERS))



def is_pure_symbol(text):
    """Skip text with no alphabetic characters in any language."""
    return not re.search(r'[A-Za-z\p{L}]', text, re.UNICODE)


def is_symbol_heavy(text):
    """Skip if text has no real words and lots of punctuation/symbols."""
    words = re.findall(r'\b\p{L}{3,}\b', text, re.UNICODE)
    if words:
        return False
    symbol_count = len(re.findall(r'[\p{P}\p{S}\d_]', text, re.UNICODE))
    return symbol_count > 0


def is_code_fragment(text):
    """Detect if a string looks like source code or a code snippet."""
    return bool(CODE_PATTERN_COMBINED.search(text))


def contains_template_markers(text):
    """Detect template syntax (Vue, Angular, Jinja2, PHP, etc.)."""
    return bool(TEMPLATE_PATTERN_COMBINED.search(text))


def has_real_words(text):
    """Check if text includes real words (length ≥ 3 characters)."""
    return re.search(r'\b\p{L}{3,}\b', text, re.UNICODE) is not None


def has_math_html_markup(element):
    """Detect HTML elements marked up with math formatting."""
    parent = element.parent
    return (
        parent.name == 'math' or
        re.search(r'\$.*?\$|\\.*?\\', parent.text or '') or
        any(cls in parent.get('class', []) for cls in ['math', 'equation', 'formula', 'katex', 'latex'])
    )


def is_math_fragment(text):
    """Detect standalone math equations or formulas."""
    equation_pattern = r'''
        (\w+\s*[=+\-*/^]\s*\S+)|        # x = y + 1
        (\d+[\+\-\*/]\d+)|              # 2 + 2
        ([a-zA-Z]+\^?\d+)|              # x^2, y³
        (\$.*?\$|\\.*?\\)           # LaTeX: $...$
    '''
    return (
        re.search(equation_pattern, text, re.VERBOSE) and not has_real_words(text)
    ) or is_symbol_heavy(text)


def contains_chinese(text):
    return re.search(r'[\u4e00-\u9fff\u3400-\u4DBF]', text) is not None

def contains_japanese(text):
    return re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', text) is not None

def contains_korean(text):
    return re.search(r'[\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318F]', text) is not None

def contains_arabic(text):
    return re.search(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]', text) is not None

def contains_hebrew(text):
    return re.search(r'[\u0590-\u05FF\uFB1D-\uFB4F]', text) is not None

def contains_thai(text):
    return re.search(r'[\u0E00-\u0E7F]', text) is not None

def contains_devanagari(text):
    return re.search(r'[\u0900-\u097F]', text) is not None

def contains_cyrillic(text):
    return re.search(r'[\u0400-\u04FF\u0500-\u052F\u2DE0-\u2DFF\uA640-\uA69F]', text) is not None

def contains_greek(text):
    return re.search(r'[\u0370-\u03FF\u1F00-\u1FFF]', text) is not None

def contains_english(text):
    return re.search(r'\\b(the|and|is|of|to|in|with|but|not|a|an|for|on|that|how|without|more|are|this|these|those)\\b',
                     text, re.IGNORECASE) is not None

def contains_french(text):
    return (
        re.search(r'[àâæçéèêëîïôœùûüÿ]', text, re.IGNORECASE) or
        re.search(r'\\b(le|la|les|un|une|des|ce|cette|est|avec|mais|pour|pas|qui|sur|vous|nous|ils|elles|sont)\\b',
                  text, re.IGNORECASE)
    )

def contains_spanish(text):
    return (
        re.search(r'[áéíóúüñ¿¡]', text, re.IGNORECASE) or
        re.search(r'\\b(el|la|los|las|un|una|que|es|con|pero|por|para|cómo|sin|más|esto|esta|estos|estas|eso|esa)\\b',
                  text, re.IGNORECASE)
    )

def contains_italian(text):
    return (
        re.search(r'[àèéìíîòóùú]', text, re.IGNORECASE) or
        re.search(r'\\b(il|lo|la|gli|le|un|una|che|è|con|ma|come|perché|senza|più|meno|sono|questo|questa|questi)\\b',
                  text, re.IGNORECASE)
    )

def contains_portuguese(text):
    return (
        re.search(r'[áàâãéêíóôõúç]', text, re.IGNORECASE) or
        re.search(r'\\b(o|a|os|as|um|uma|que|é|com|mas|por|para|como|sem|mais|são|isto|esta|estes|estas|esse|essa)\\b',
                  text, re.IGNORECASE)
    )

def contains_german(text):
    return (
        re.search(r'[äöüß]', text, re.IGNORECASE) or
        re.search(r'\\b(der|die|das|ein|eine|ist|mit|aber|und|nicht|für|ohne|warum|wie|mehr|sind|diese|dieser)\\b',
                  text, re.IGNORECASE)
    )

def contains_dutch(text):
    return (
        re.search(r'[áàéèëïöüĳ]', text, re.IGNORECASE) or
        re.search(r'\\b(de|het|een|is|zijn|en|of|maar|voor|met|door|wat|wie|waar|hoe|waarom|wanneer)\\b',
                  text, re.IGNORECASE)
    )

def contains_polish(text):
    return (
        re.search(r'[ąćęłńóśźż]', text, re.IGNORECASE) or
        re.search(r'\\b(i|w|z|na|to|że|a|jest|się|do|o|jak|nie|co|dla|tak|przez|tylko|albo)\\b',
                  text, re.IGNORECASE)
    )


def is_exception_language(text):
    """
    Detect if the text contains characters that clearly require switching from the default language.
    This is used for early rejection of symbols or skipping unnecessary parsing.
    """
    if contains_chinese(text):
        return "zh"
    elif contains_arabic(text):
        return "ar"
    elif contains_hebrew(text):
        return "xx"
    elif contains_thai(text):
        return "xx"
    elif contains_devanagari(text):
        return "xx"
    elif contains_korean(text):
        return "ko"
    elif contains_japanese(text):
        return "ja"
    return None


def detectis_exception_language(text):
    """
    More robust heuristic to identify the actual language of the text for spaCy model routing.
    """
    if contains_chinese(text):
        return "zh"
    elif contains_english(text):
        return "en"
    elif contains_arabic(text):
        return "ar"
    elif contains_cyrillic(text):
        return "ru"
    elif contains_greek(text):
        return "el"
    elif contains_hebrew(text):
        return "xx"
    elif contains_thai(text):
        return "xx"
    elif contains_devanagari(text):
        return "xx"
    elif contains_japanese(text):
        return "ja"
    elif contains_korean(text):
        return "ko"
    elif contains_french(text):
        return "fr"
    elif contains_spanish(text):
        return "es"
    elif contains_italian(text):
        return "it"
    elif contains_german(text):
        return "de"
    elif contains_dutch(text):
        return "nl"
    elif contains_portuguese(text):
        return "pt"
    elif contains_polish(text):
        return "pl"
    return None


def has_do_not_translate_marker(element):
    """
    Walks up the DOM tree to check for attributes or classes indicating that the element should not be translated.
    """
    current = element
    while current:
        if current.get("translate", "").lower() == "no":
            return True

        classes = current.get("class", [])
        if isinstance(classes, str):
            classes = classes.split()

        no_translate_classes = [
            "notranslate", "no-translate", "do-not-translate",
            "translation-skip", "translation-ignore"
        ]
        if any(cls in classes for cls in no_translate_classes):
            return True

        if current.get("data-translate") == "no" or current.get("data-i18n-skip") == "true":
            return True

        current = current.parent
    return False


def is_translatable_text(tag):
    """
    Determines whether a given NavigableString element should be considered for translation.
    """
    current_element = tag.parent
    translate_override = None

    while current_element is not None:
        current_translate = current_element.get("translate", "").lower()
        if current_translate in {"yes", "no"}:
            translate_override = current_translate
            break
        current_element = current_element.parent

    text = tag.strip()
    if not text:
        return False

    if has_do_not_translate_marker(tag):
        return False

    if contains_template_markers(text) or is_code_fragment(text):
        return False

    if not is_exception_language(text):
        if (
            is_pure_symbol(text) or
            is_math_fragment(text) or
            has_math_html_markup(tag)
        ):
            return False

    if translate_override == "no":
        return False

    parent_tag = tag.parent.name if tag.parent else None
    default_translatable = (
        parent_tag in TRANSLATABLE_TAGS and
        parent_tag not in SKIP_PARENTS and
        not isinstance(tag, Comment)
    )

    if translate_override == "yes":
        return True

    return default_translatable


def load_spacy_model(lang_code):
    """
    Load the appropriate spaCy language model, downloading it if necessary.
    """
    if lang_code not in SPACY_MODELS:
        print(f"Unsupported language '{lang_code}'. Choose from: {', '.join(SPACY_MODELS)}.")
        sys.exit(1)

    model_name = SPACY_MODELS[lang_code]

    try:
        nlp = spacy.load(model_name)
    except OSError:
        print(f"spaCy model '{model_name}' not found. Downloading...")
        subprocess.run(["python", "-m", "spacy", "download", model_name], check=True)
        nlp = spacy.load(model_name)

    if "parser" not in nlp.pipe_names and "sentencizer" not in nlp.pipe_names:
        nlp.add_pipe("sentencizer", first=True)

    return nlp


def process_text_block(block_id, text, default_nlp):
    """
    Tokenizes a block of text into sentences and words, with optional language switching.
    Returns structured, flattened, and sentence-token mappings.
    """
    if is_code_fragment(text):
        return None, None, None

    lang_code = detectis_exception_language(text)
    nlp = default_nlp if not lang_code else load_spacy_model(lang_code)
    detected_language = lang_code or "default"

    structured = {}
    flattened = {}
    sentence_tokens = []

    doc = nlp(text)
    for s_idx, sent in enumerate(doc.sents, 1):
        s_key = f"S{s_idx}"
        sentence_id = f"{block_id}_{s_key}"
        sentence_text = sent.text
        flattened[sentence_id] = sentence_text
        structured[s_key] = {"text": sentence_text, "words": {}}
        sentence_tokens.append((sentence_id, sentence_text))

        for w_idx, token in enumerate(sent, 1):
            w_key = f"W{w_idx}"
            word_id = f"{sentence_id}_{w_key}"
            flattened[word_id] = token.text
            structured[s_key]["words"][w_key] = {
                "text": token.text,
                "pos": token.pos_,
                "language": detected_language,
                "ent": token.ent_type_ or None,
                "pinyin": (
                    " ".join(lazy_pinyin(token.text))
                    if contains_chinese(token.text)
                    else None
                )
            }

    return structured, flattened, sentence_tokens


def extract_from_jsonld(obj, block_counter, nlp, structured_output, flattened_output):
    """
    Recursively traverses a JSON-LD object (dict or list) and replaces eligible
    string fields with translatable sentence token IDs.

    Updates:
    - Uses updated TRANSLATABLE_JSONLD_KEYS
    - Avoids JSONLD_EXCLUDE_KEYS
    - Skips @context, @type, and technical fields like 'url', 'datePublished'
    """
    if isinstance(obj, dict):
        for key in list(obj.keys()):
            value = obj[key]
            key_lc = key.lower()

            if isinstance(value, str):
                # Skip excluded fields or structural JSON-LD keys
                if key_lc in JSONLD_EXCLUDE_KEYS or key_lc.startswith("@"):
                    continue

                # Translate if it's in the known keys or heuristically valid
                if (
                    key_lc in TRANSLATABLE_JSONLD_KEYS or
                    all(x not in key_lc for x in ["url", "date", "time", "type"])
                ):
                    block_id = f"BLOCK_{block_counter}"
                    structured, flattened, tokens = process_text_block(block_id, value, nlp)

                    if tokens:
                        # Replace original string with first sentence token ID
                        obj[key] = tokens[0][0]
                        structured_output[block_id] = {
                            "jsonld": key,
                            "tokens": structured
                        }
                        flattened_output.update(flattened)
                        block_counter += 1

            elif isinstance(value, (dict, list)):
                # Recurse into nested objects or arrays
                block_counter = extract_from_jsonld(value, block_counter, nlp, structured_output, flattened_output)

    elif isinstance(obj, list):
        for i in range(len(obj)):
            block_counter = extract_from_jsonld(obj[i], block_counter, nlp, structured_output, flattened_output)

    return block_counter


def extract_translatable_html(input_path, lang_code):
    nlp = load_spacy_model(lang_code)

    with open(input_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html5lib")

    structured_output = {}
    flattened_output = {}
    block_counter = 1

    # --- TEXT ELEMENTS ---
    for element in list(soup.find_all(string=True)):
        if is_translatable_text(element):
            text = element.strip()
            if not text:
                continue

            structured, flattened, sentence_tokens = process_text_block(f"BLOCK_{block_counter}", text, nlp)

            if sentence_tokens:
                structured_output[f"BLOCK_{block_counter}"] = {
                    "tag": element.parent.name,
                    "tokens": structured
                }
                flattened_output.update(flattened)
                element.replace_with(NavigableString(sentence_tokens[0][0]))
                block_counter += 1

    # --- ATTRIBUTES ---
    for tag in soup.find_all():
        for attr in TRANSLATABLE_ATTRS:
            if (
                attr in tag.attrs and
                isinstance(tag[attr], str) and
                attr not in BLOCKED_ATTRS
            ):
                value = tag[attr].strip()
                if value:
                    structured, flattened, sentence_tokens = process_text_block(f"BLOCK_{block_counter}", value, nlp)
                    if sentence_tokens:
                        structured_output[f"BLOCK_{block_counter}"] = {
                            "attr": attr,
                            "tokens": structured
                        }
                        flattened_output.update(flattened)
                        tag[attr] = sentence_tokens[0][0]
                        block_counter += 1

    # --- META TAGS ---
    for meta in soup.find_all("meta"):
        name = meta.get("name", "").lower()
        prop = meta.get("property", "").lower()
        content = meta.get("content", "").strip()

        if name in EXCLUDED_META_NAMES or prop in EXCLUDED_META_PROPERTIES:
            continue

        if content and (
            (name and name in SEO_META_FIELDS.get("name", set())) or
            (prop and prop in SEO_META_FIELDS.get("property", set()))
        ):
            structured, flattened, sentence_tokens = process_text_block(f"BLOCK_{block_counter}", content, nlp)
            if sentence_tokens:
                structured_output[f"BLOCK_{block_counter}"] = {
                    "meta": name or prop,
                    "tokens": structured
                }
                flattened_output.update(flattened)
                meta["content"] = sentence_tokens[0][0]
                block_counter += 1

    # --- <TITLE> TAG ---
    if soup.title and soup.title.string and soup.title.string.strip():
        text = soup.title.string.strip()
        structured, flattened, sentence_tokens = process_text_block(f"BLOCK_{block_counter}", text, nlp)
        if sentence_tokens:
            structured_output[f"BLOCK_{block_counter}"] = {
                "tag": "title",
                "tokens": structured
            }
            flattened_output.update(flattened)
            soup.title.string.replace_with(sentence_tokens[0][0])
            block_counter += 1

    # --- JSON-LD SCRIPTS ---
    for script_tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            raw_json = script_tag.string.strip()
            data = json.loads(raw_json)
            block_counter = extract_from_jsonld(data, block_counter, nlp, structured_output, flattened_output)
            script_tag.string.replace_with(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"⚠️ Failed to parse JSON-LD: {e}")

    # --- SAVE OUTPUTS ---

    # Flattened summary with segments
    reformatted_flat = {}
    for block_id, data in structured_output.items():
        text = " ".join(s["text"] for s in data["tokens"].values())
        segments = {
            f"{block_id}_{s_key}": s_data["text"]
            for s_key, s_data in data["tokens"].items()
        }
        block_type = data.get("tag") or data.get("attr") or data.get("meta") or data.get("jsonld") or "unknown"
        reformatted_flat[block_id] = {
            "type": block_type,
            "text": text,
            "segments": segments
        }

    with open("translatable_structured.json", "w", encoding="utf-8") as f:
        json.dump(structured_output, f, indent=2, ensure_ascii=False)

    with open("translatable_flat.json", "w", encoding="utf-8") as f:
        json.dump(reformatted_flat, f, indent=2, ensure_ascii=False)

    with open("translatable_flat_sentences.json", "w", encoding="utf-8") as f:
        flat_sentences = {
            k: v for k, v in flattened_output.items()
            if "_S" in k and "_W" not in k
        }
        json.dump(flat_sentences, f, indent=2, ensure_ascii=False)

    with open("non_translatable.html", "w", encoding="utf-8") as f:
        f.write(str(soup))

    print("✅ Step 1 complete: saved output files.")


if __name__ == "__main__":
    SUPPORTED_LANGS = ", ".join(sorted(SPACY_MODELS.keys()))

    parser = argparse.ArgumentParser(
        description="Extract translatable text from HTML and generate structured output.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument(
        "input_file",
        help="Path to the HTML file to process"
    )

    parser.add_argument(
        "--lang",
        choices=SPACY_MODELS.keys(),
        required=True,
        metavar="LANG_CODE",
        help=f"""\
Primary language of the document (REQUIRED).
Supported codes: {SUPPORTED_LANGS}
Examples: --lang en (English), --lang zh (Chinese), --lang fr (French)"""
    )

    parser.add_argument(
        "--secondary-lang",
        choices=SPACY_MODELS.keys(),
        metavar="LANG_CODE",
        help=f"""\
Optional secondary language for mixed-content detection.
Supported codes: {SUPPORTED_LANGS}
Examples: --secondary-lang es (Spanish), --secondary-lang de (German)"""
    )

    args = parser.parse_args()

    if args.secondary_lang and args.secondary_lang == args.lang:
        parser.error("Primary and secondary languages cannot be the same!")

    extract_translatable_html(args.input_file, args.lang)
