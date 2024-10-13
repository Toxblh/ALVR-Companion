import os
import subprocess
from dotenv import load_dotenv
from openai import OpenAI
import sys

# Загрузка переменных окружения из .env файла
load_dotenv()

# Получение API ключа OpenAI из переменных окружения
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

skip_translation = False
# Путь к директории с исходными файлами
source_dir = '.'
# Путь к директории для хранения файлов перевода
locale_dir = 'locale'
# Имя домена перевода
domain = 'alvr_companion'
# Email переводчика
translator_email = 'toxblh@gmail.com'

# Создание директории для хранения файлов перевода, если она не существует
os.makedirs(locale_dir, exist_ok=True)

# Генерация файла .pot с помощью xgettext
subprocess.run([
    'xgettext',
    '--language=Python',
    '--keyword=_',
    '--output={}/{}.pot'.format(locale_dir, domain),
    '--from-code=UTF-8'
] + [os.path.join(source_dir, f) for f in os.listdir(source_dir) if f.endswith('.py')])


# Проверка аргументов командной строки
if len(sys.argv) > 1 and sys.argv[1] == 'compile':
    skip_translation = True
else:
    skip_translation = False

# Топ-10 популярных языков
languages = ['en', 'zh', 'es', 'hi', 'ar', 'bn', 'fr', 'ru', 'pt', 'de']

# Функция для перевода текста с помощью ChatGPT
def translate_text(text, target_language):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": f"Translate the following text to {target_language}. Follow rules: 'msgid' - stay original without changes and 'msgstr' contain translation. Return only plain text without any formatting"},
            {"role": "user", "content": text}
        ],
        max_tokens=10000
    )
    translated_text = response.choices[0].message.content.strip()
    return translated_text.replace('```', '')

if not skip_translation:
    # Создание файлов .po для каждого языка и автоперевод
    for lang in languages:
        lang_dir = os.path.join(locale_dir, lang, 'LC_MESSAGES')
        os.makedirs(lang_dir, exist_ok=True)
        po_file = os.path.join(lang_dir, '{}.po'.format(domain))
        if os.path.exists(po_file):
            # Merge existing .po file with new .pot file
            subprocess.run([
                'msgmerge',
                '--update',
                '--backup=none',
                po_file,
                '{}/{}.pot'.format(locale_dir, domain)
            ])
        else:
            # Initialize new .po file
            subprocess.run([
                'msginit',
                '--input={}/{}.pot'.format(locale_dir, domain),
                '--output-file={}'.format(po_file),
                '--locale={}'.format(lang),
                '--no-translator'
            ])
        
        # Добавление email переводчика в заголовок файла .po
        with open(po_file, 'r+', encoding='utf-8') as f:
            content = f.read()
            content = content.replace('LAST-TRANSLATOR', f'LAST-TRANSLATOR {translator_email}')
            translated_content = translate_text(content, lang)
            f.seek(0)
            f.write(translated_content)
            f.truncate()

# Компиляция файлов .po в .mo
for lang in languages:
    lang_dir = os.path.join(locale_dir, lang, 'LC_MESSAGES')
    po_file = os.path.join(lang_dir, '{}.po'.format(domain))
    mo_file = os.path.join(lang_dir, '{}.mo'.format(domain))
    subprocess.run([
        'msgfmt',
        '--output-file={}'.format(mo_file),
        po_file
    ])