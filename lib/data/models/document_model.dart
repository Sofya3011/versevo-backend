class DocumentModel {
  final int id;
  final String title;
  final String filename;
  final String? content;
  final String? translatedContent;
  final String language;
  final String fileType;
  final int fileSize;
  final int wordCount;
  final int charCount;
  final int chapterCount;
  final int readingTimeMinutes;
  final DateTime createdAt;
  final DateTime updatedAt;
  final List<Map<String, dynamic>> chapters;
  final Map<String, dynamic> metadata;

  DocumentModel({
    required this.id,
    required this.title,
    required this.filename,
    required this.content,
    this.translatedContent,
    required this.language,
    required this.fileType,
    required this.fileSize,
    required this.wordCount,
    required this.charCount,
    required this.chapterCount,
    required this.readingTimeMinutes,
    required this.createdAt,
    required this.updatedAt,
    required this.chapters,
    required this.metadata,
  });

  factory DocumentModel.fromJson(Map<String, dynamic> json) {
    final title = json['title'] ??
        json['filename']?.toString().split('.').first ??
        'Без названия';

    // Обработка content - убеждаемся, что это строка
    final content = json['content']?.toString() ?? '';

    // Получаем translatedContent
    final translatedContent = json['translated_content']?.toString();

    // ВАЖНОЕ ИСПРАВЛЕНИЕ: Получаем file_type из реального имени файла
    String fileType = 'txt'; // значение по умолчанию

    // 1. Пробуем получить из поля file_type
    if (json['file_type'] != null && json['file_type'].toString().isNotEmpty) {
      fileType = json['file_type'].toString().toLowerCase();
    }
    // 2. Если нет, пробуем получить из поля fileType
    else if (json['fileType'] != null && json['fileType'].toString().isNotEmpty) {
      fileType = json['fileType'].toString().toLowerCase();
    }
    // 3. Если все еще нет, извлекаем из имени файла
    else if (json['filename'] != null) {
      final filenameStr = json['filename'].toString();
      if (filenameStr.contains('.')) {
        final ext = filenameStr.split('.').last.toLowerCase();
        // Проверяем, что это действительно расширение файла
        if (ext.length <= 5 && !ext.contains('/') && !ext.contains('\\')) {
          fileType = ext;
        }
      }
    }

    // Обработка дат
    final createdAt = json['created_at'] != null
        ? DateTime.parse(json['created_at'].toString())
        : DateTime.now();

    final updatedAt = json['updated_at'] != null
        ? DateTime.parse(json['updated_at'].toString())
        : createdAt;

    // Обработка chapters
    final chapters = (json['chapters'] is List)
        ? List<Map<String, dynamic>>.from(json['chapters'])
        : <Map<String, dynamic>>[];

    // Обработка metadata
    final metadata = (json['metadata'] is Map)
        ? Map<String, dynamic>.from(json['metadata'])
        : <String, dynamic>{};

    return DocumentModel(
      id: (json['id'] as num).toInt(),
      title: title,
      filename: json['filename']?.toString() ?? 'unknown',
      content: content,
      translatedContent: translatedContent,
      language: json['language']?.toString() ?? 'ru',
      fileType: fileType,
      fileSize: (json['file_size'] as num?)?.toInt() ?? 0,
      wordCount: (json['word_count'] as num?)?.toInt() ?? 0,
      charCount: (json['char_count'] as num?)?.toInt() ?? 0,
      chapterCount: (json['chapter_count'] as num?)?.toInt() ?? 0,
      readingTimeMinutes: (json['reading_time_minutes'] as num?)?.toInt() ?? 0,
      createdAt: createdAt,
      updatedAt: updatedAt,
      chapters: chapters,
      metadata: metadata,
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'title': title,
    'filename': filename,
    'content': content,
    'translated_content': translatedContent,
    'language': language,
    'file_type': fileType,
    'file_size': fileSize,
    'word_count': wordCount,
    'char_count': charCount,
    'chapter_count': chapterCount,
    'reading_time_minutes': readingTimeMinutes,
    'created_at': createdAt.toIso8601String(),
    'updated_at': updatedAt.toIso8601String(),
    'chapters': chapters,
    'metadata': metadata,
  };
}