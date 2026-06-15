import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:dio/dio.dart';
import 'package:versevo_app/data/models/document_model.dart';
import 'package:versevo_app/data/api/document_api.dart';

class DocumentNote {
  final int id;
  final int documentId;
  final int chapterIndex;
  final String text;
  final String? selectedText;
  final int? textPosition;
  final DateTime createdAt;

  DocumentNote({
    required this.id,
    required this.documentId,
    required this.chapterIndex,
    required this.text,
    this.selectedText,
    this.textPosition,
    required this.createdAt,
  });

  Map<String, dynamic> toJson() => {
    'id': id,
    'documentId': documentId,
    'chapterIndex': chapterIndex,
    'text': text,
    'selectedText': selectedText,
    'textPosition': textPosition,
    'createdAt': createdAt.toIso8601String(),
  };

  factory DocumentNote.fromJson(Map<String, dynamic> json) => DocumentNote(
    id: json['id'] ?? DateTime.now().millisecondsSinceEpoch,
    documentId: json['documentId'],
    chapterIndex: json['chapterIndex'],
    text: json['text'],
    selectedText: json['selectedText'],
    textPosition: json['textPosition'],
    createdAt: DateTime.parse(json['createdAt']),
  );
}

class ReadingProgress {
  final int documentId;
  final int chapterIndex;
  final double scrollPosition;
  final DateTime timestamp;

  ReadingProgress({
    required this.documentId,
    required this.chapterIndex,
    required this.scrollPosition,
    required this.timestamp,
  });

  Map<String, dynamic> toJson() => {
    'documentId': documentId,
    'chapterIndex': chapterIndex,
    'scrollPosition': scrollPosition,
    'timestamp': timestamp.toIso8601String(),
  };

  factory ReadingProgress.fromJson(Map<String, dynamic> json) =>
      ReadingProgress(
        documentId: json['documentId'],
        chapterIndex: json['chapterIndex'],
        scrollPosition: json['scrollPosition'],
        timestamp: DateTime.parse(json['timestamp']),
      );
}

class LoadingDot extends StatefulWidget {
  final int delay;

  const LoadingDot({required this.delay, super.key});

  @override
  State<LoadingDot> createState() => _LoadingDotState();
}

class _LoadingDotState extends State<LoadingDot> {
  bool _visible = false;

  @override
  void initState() {
    super.initState();
    _startAnimation();
  }

  void _startAnimation() async {
    await Future.delayed(Duration(milliseconds: widget.delay));
    if (mounted) {
      setState(() => _visible = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedOpacity(
      opacity: _visible ? 1.0 : 0.3,
      duration: const Duration(milliseconds: 300),
      child: Container(
        width: 10,
        height: 10,
        margin: const EdgeInsets.symmetric(horizontal: 3),
        decoration: BoxDecoration(color: Colors.blue, shape: BoxShape.circle),
      ),
    );
  }
}

class DocumentReaderScreen extends StatefulWidget {
  final DocumentModel document;
  const DocumentReaderScreen({super.key, required this.document});

  @override
  State<DocumentReaderScreen> createState() => _DocumentReaderScreenState();
}

class _DocumentReaderScreenState extends State<DocumentReaderScreen> {
  int _currentChapterIndex = 0;
  bool _showTranslation = false;
  double _fontSize = 18.0;
  double _lineHeight = 1.8;
  String _fontFamily = 'Inter';
  bool _isTranslating = false;
  String? _translatedContent;
  // ignore: unused_field
  String? _translationError;

  int _translationProgress = 0;
  int _currentChunk = 0;
  int _totalChunks = 0;
  final List<String> _translatedChunks = [];
  List<String> _originalChunks = [];

  final ScrollController _scrollController = ScrollController();
  final GlobalKey _contentKey = GlobalKey();
  double _lastScrollPosition = 0.0;
  Timer? _saveProgressTimer;
  final ValueNotifier<double> _scrollProgressNotifier = ValueNotifier<double>(
    0.0,
  );

  bool _isDarkMode = false;
  Color _backgroundColor = Colors.white;
  Color _textColor = Colors.black87;

  Color _buttonColor = const Color(0xFF4F6CF7);

  // ignore: unused_field
  TextSelection? _selection;
  String? _selectedText;
  int? _selectedTextPosition;
  final List<DocumentNote> _notes = [];

  final Map<String, String> _translationCache = {};
  List<Map<String, dynamic>> _autoChapters = [];
  final DocumentApi _documentApi = DocumentApi();
  final Set<int> _bookmarkedChapters = {};

  @override
  void initState() {
    super.initState();
    _initializeDocument();
    _loadReadingProgress();
    _loadNotes();
    _loadBookmarks();
    _scrollController.addListener(_onScroll);
  }

  @override
  void dispose() {
    _saveProgressTimer?.cancel();
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    _scrollProgressNotifier.dispose();
    super.dispose();
  }

  void _initializeDocument() {
    if (widget.document.chapters.isEmpty) {
      _autoChapters = _splitIntoChapters(widget.document.content ?? '');
    }
  }

  List<Map<String, dynamic>> _splitIntoChapters(String content) {
    final List<Map<String, dynamic>> chapters = [];

    if (content.isEmpty) {
      chapters.add({'title': 'Документ', 'content': 'Нет содержимого'});
      return chapters;
    }

    final paragraphs = content
        .split('\n\n')
        .where((p) => p.trim().isNotEmpty)
        .toList();

    if (paragraphs.isEmpty) {
      chapters.add({'title': 'Документ', 'content': content});
      return chapters;
    }

    final markerRegex = RegExp(
      r'^\s*(?:'
      r'(?:Глава|Гл\.)\s*[IVXLCDM\d]+[\.\:\s]|'
      r'(?:Chapter|Ch\.)\s*[IVXLCDM\d]+[\.\:\s]|'
      r'(?:Раздел)\s*[IVXLCDM\d]+[\.\:\s]|'
      r'(?:Section)\s*[IVXLCDM\d]+[\.\:\s]|'
      r'(?:Часть|Part)\s*[IVXLCDM\d]+[\.\:\s]|'
      r'§\s*\d+|'
      r'#{1,3}\s+[IVXLCDM\d]|'
      r')',
    );

    final hasMarkers = paragraphs.any((p) => markerRegex.hasMatch(p.trim()));

    if (hasMarkers) {
      StringBuffer currentContent = StringBuffer();
      String? currentTitle;

      for (final paragraph in paragraphs) {
        final trimmed = paragraph.trim();
        final isMarker = markerRegex.hasMatch(trimmed);

        if (isMarker && currentContent.isNotEmpty) {
          chapters.add({
            'title': currentTitle ?? 'Часть ${chapters.length + 1}',
            'content': currentContent.toString(),
          });
          currentContent.clear();
        }
        if (isMarker) {
          currentTitle = trimmed;
        }
        currentContent.writeln(paragraph);
        currentContent.writeln();
      }

      if (currentContent.isNotEmpty) {
        chapters.add({
          'title': currentTitle ?? 'Часть ${chapters.length + 1}',
          'content': currentContent.toString(),
        });
      }
    } else {
      const int paragraphsPerChapter = 12;
      int currentChapter = 1;
      StringBuffer currentContent = StringBuffer();

      for (int i = 0; i < paragraphs.length; i++) {
        currentContent.writeln(paragraphs[i]);
        currentContent.writeln();

        if ((i + 1) % paragraphsPerChapter == 0 && i < paragraphs.length - 1) {
          chapters.add({
            'title': 'Часть $currentChapter',
            'content': currentContent.toString(),
          });
          currentChapter++;
          currentContent.clear();
        }
      }

      if (currentContent.isNotEmpty) {
        chapters.add({
          'title': 'Часть $currentChapter',
          'content': currentContent.toString(),
        });
      }
    }

    if (chapters.isEmpty) {
      chapters.add({'title': 'Документ', 'content': content});
    }

    return chapters;
  }

  String get _currentContent {
    if (widget.document.chapters.isNotEmpty) {
      return widget.document.chapters[_currentChapterIndex]['content']
              ?.toString() ??
          widget.document.content ??
          'Нет содержимого';
    } else if (_autoChapters.isNotEmpty) {
      return _autoChapters[_currentChapterIndex]['content']?.toString() ??
          widget.document.content ??
          'Нет содержимого';
    }
    return widget.document.content ?? 'Нет содержимого';
  }

  String get _currentTitle {
    if (widget.document.chapters.isNotEmpty) {
      return widget.document.chapters[_currentChapterIndex]['title']
              ?.toString() ??
          'Глава ${_currentChapterIndex + 1}';
    } else if (_autoChapters.isNotEmpty) {
      return _autoChapters[_currentChapterIndex]['title']?.toString() ??
          'Часть ${_currentChapterIndex + 1}';
    }
    return widget.document.title;
  }

  int get _totalChapters {
    if (widget.document.chapters.isNotEmpty) {
      return widget.document.chapters.length;
    }
    return _autoChapters.length;
  }

  List<String> _splitTextIntoChunks(String text, {int chunkSize = 800}) {
    final List<String> chunks = [];

    if (text.isEmpty) return chunks;

    final sentences = text.split(RegExp(r'(?<=[.!?])\s+'));
    StringBuffer currentChunk = StringBuffer();

    for (final sentence in sentences) {
      if (currentChunk.length + sentence.length < chunkSize) {
        currentChunk.writeln(sentence);
      } else {
        if (currentChunk.isNotEmpty) {
          chunks.add(currentChunk.toString());
          currentChunk.clear();
        }
        if (sentence.length > chunkSize) {
          for (int i = 0; i < sentence.length; i += chunkSize) {
            final end = min(i + chunkSize, sentence.length);
            chunks.add(sentence.substring(i, end));
          }
        } else {
          currentChunk.writeln(sentence);
        }
      }
    }

    if (currentChunk.isNotEmpty) {
      chunks.add(currentChunk.toString());
    }

    return chunks;
  }

  String _getTail(List<String> chunks, int index, {int tailLength = 200}) {
    if (index <= 0 || chunks.isEmpty) return '';
    final prev = chunks[index - 1];
    if (prev.length <= tailLength) return prev;
    return prev.substring(prev.length - tailLength);
  }

  String _postProcessTranslation(String text) {
    text = text.replaceAll(RegExp(r'^Перевод[^:]*:\s*', multiLine: true), '');
    text = text.replaceAll(
      RegExp(r'^Chapter\s+\d+[:\s]*', multiLine: true),
      '',
    );
    text = text.replaceAll(RegExp(r'^Глава\s+\d+[:\s]*', multiLine: true), '');
    text = text.replaceAll(
      RegExp(r'^Translation[^:]*:\s*', multiLine: true),
      '',
    );
    text = text.replaceAll(RegExp(r'\[.*?\]'), '');
    text = text.replaceAll(
      RegExp(r'\(.*?перевод.*?\)', caseSensitive: false),
      '',
    );
    text = text.replaceAllMapped(RegExp(r'\b(\w+)\s+\1\b'), (m) => m[1]!);
    text = text.replaceAll(RegExp(r'\.{4,}'), '...');
    text = text.replaceAll(RegExp(r'\n{3,}'), '\n\n');
    text = text
        .split('\n')
        .map((line) {
          line = line.trim();
          if (line.isEmpty) return '';
          return line[0].toUpperCase() + line.substring(1);
        })
        .join('\n');
    return text.trim();
  }

  Future<void> _translateFullChapter() async {
    if (_showTranslation) {
      setState(() => _showTranslation = false);
      return;
    }

    final cacheKey = '${widget.document.id}_$_currentChapterIndex';

    if (_translationCache.containsKey(cacheKey)) {
      debugPrint(
        'Используем кэшированный перевод для главы $_currentChapterIndex',
      );
      setState(() {
        _translatedContent = _translationCache[cacheKey];
        _showTranslation = true;
      });
      _showSnackbar('Использован кэшированный перевод', Colors.green);
      return;
    }

    final contentToTranslate = _currentContent;

    setState(() {
      _isTranslating = true;
      _translationProgress = 0;
      _currentChunk = 0;
      _translatedChunks.clear();
      _originalChunks = _splitTextIntoChunks(contentToTranslate);
      _totalChunks = _originalChunks.length;
    });

    debugPrint('Начинаем перевод главы ${_currentChapterIndex + 1}');
    debugPrint('Длина текста: ${contentToTranslate.length} символов');
    debugPrint('Разбито на $_totalChunks чанков');

    try {
      for (int i = 0; i < _originalChunks.length; i++) {
        final chunk = _originalChunks[i];

        setState(() {
          _currentChunk = i + 1;
          _translationProgress = ((i + 1) / _totalChunks * 100).round();
        });

        debugPrint(
          'Переводим чанк ${i + 1}/$_totalChunks (${chunk.length} символов)',
        );

        final tail = _getTail(_originalChunks, i);
        final contextualChunk = tail.isNotEmpty ? '$tail\n\n$chunk' : chunk;
        final cleanChunk = _stripImagesForApi(contextualChunk);

        Map<String, dynamic>? response;
        for (int attempt = 1; attempt <= 2; attempt++) {
          try {
            response = await _documentApi.translateText(
              cleanChunk,
              'ru',
              sourceLanguage: widget.document.language.isNotEmpty
                  ? widget.document.language
                  : 'en',
              style: 'artistic',
            );
            break;
          } catch (e) {
            debugPrint('Попытка $attempt не удалась: $e');
            if (attempt < 2) {
              await Future.delayed(const Duration(seconds: 1));
            }
          }
        }

        if (response != null) {
          String? translatedText;
          if (response.containsKey('translated_text')) {
            translatedText = response['translated_text'];
          } else if (response.containsKey('translatedText')) {
            translatedText = response['translatedText'];
          }

          if (translatedText != null && translatedText.isNotEmpty) {
            String cleaned = translatedText;
            if (tail.isNotEmpty) {
              final lines = cleaned.split('\n');
              if (lines.length > 1) {
                cleaned = lines.sublist(1).join('\n');
              }
            }
            cleaned = _postProcessTranslation(cleaned);
            _translatedChunks.add(cleaned);
            debugPrint('Чанк ${i + 1} переведен успешно');
          } else {
            _translatedChunks.add(_createFallbackTranslation(chunk));
            debugPrint('Чанк ${i + 1}: использован fallback перевод');
          }
        } else {
          _translatedChunks.add(_createFallbackTranslation(chunk));
          debugPrint('Чанк ${i + 1}: использован fallback перевод');
        }

        if (i < _originalChunks.length - 1) {
          await Future.delayed(const Duration(milliseconds: 300));
        }
      }

      String fullTranslation = _translatedChunks.join('\n\n');

      final polished = await _polishTranslation(fullTranslation);
      if (polished != null && polished.isNotEmpty) {
        fullTranslation = polished;
      }

      _translationCache[cacheKey] = fullTranslation;

      setState(() {
        _translatedContent = fullTranslation;
        _showTranslation = true;
        _isTranslating = false;
        _translationProgress = 100;
      });

      debugPrint('Перевод главы завершен! Всего чанков: $_totalChunks');
      _showSnackbar('Глава полностью переведена!', Colors.green);
    } catch (e) {
      debugPrint('Критическая ошибка перевода: $e');

      String partialTranslation = '';
      if (_translatedChunks.isNotEmpty) {
        partialTranslation = _translatedChunks.join('\n\n');
        if (partialTranslation.isNotEmpty) {
          partialTranslation += '\n\n[Перевод прерван: ${e.toString()}]';
        }
      } else {
        partialTranslation = _createRealFallbackTranslation(contentToTranslate);
      }

      setState(() {
        _translatedContent = partialTranslation;
        _showTranslation = true;
        _isTranslating = false;
        _translationError = e.toString();
      });

      _showSnackbar('Перевод не завершен', Colors.orange);
    }
  }

  String _cleanContentForDisplay(String text) {
    text = text.replaceAll(RegExp(r'\r\n?'), '\n');
    text = text.replaceAll(RegExp(r'[ \t]+'), ' ');
    text = text.replaceAll(RegExp(r'\n{3,}'), '\n\n');
    text = text.replaceAll(RegExp(r'^\s+', multiLine: true), '');
    text = text.replaceAll(RegExp(r'\s+$', multiLine: true), '');
    text = text.replaceAll(RegExp(r'^ERROR:.*$', multiLine: true), '');
    text = text.replaceAll(RegExp(r'^Error:.*$', multiLine: true), '');
    text = text.replaceAll(RegExp(r'\[Перевод недоступен\]'), '');
    text = text.replaceAll(RegExp(r'^\d+\.\s*', multiLine: true), '');
    text = text.replaceAll(RegExp(r'_{3,}'), '');
    text = text.replaceAll(RegExp(r'>{2,}'), '');
    text = text.replaceAll(RegExp(r'<(?!/?img\b)[^>]*>', caseSensitive: false), '');
    text = text.replaceAllMapped(RegExp(r'\n([а-я])'), (m) => ' ${m[1]}');
    return text.trim();
  }

  List<InlineSpan> _buildImageInlineSpans(
    String text,
    List<DocumentNote> highlights,
    TextStyle baseStyle,
  ) {
    final htmlImg = RegExp(
      '<img\\s+[^>]*src=["\']([^"\']+)["\'][^>]*>',
      caseSensitive: false,
    );
    final mdImg = RegExp(
      '!\\[([^\\]]*)\\]\\(([^)]+)\\)',
    );
    text = text.replaceAllMapped(mdImg, (m) => '<img src="${m[2]}">');
    final matches = htmlImg.allMatches(text).toList();
    if (matches.isEmpty) {
      return _buildTextSpans(text, highlights, baseStyle);
    }

    final spans = <InlineSpan>[];
    int lastEnd = 0;

    for (int i = 0; i < matches.length; i++) {
      final m = matches[i];
      if (m.start > lastEnd) {
        spans.addAll(
          _buildTextSpans(text.substring(lastEnd, m.start), highlights, baseStyle, offset: lastEnd),
        );
      }
      final src = m.group(1)!;
      spans.add(
        WidgetSpan(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: _buildContentImage(src),
            ),
          ),
        ),
      );
      lastEnd = m.end;
      if (i == matches.length - 1 && lastEnd < text.length) {
        spans.addAll(
          _buildTextSpans(text.substring(lastEnd), highlights, baseStyle, offset: lastEnd),
        );
      }
    }
    return spans;
  }

  Widget _buildContentImage(String src) {
    final uri = Uri.tryParse(src);
    if (uri != null && uri.hasScheme) {
      return GestureDetector(
        onTap: () => _showImagePreview(src),
        child: Image.network(
          src,
          fit: BoxFit.contain,
          width: double.infinity,
          loadingBuilder: (_, child, progress) {
            if (progress == null) return child;
            return Container(
              height: 200,
              color: _isDarkMode ? const Color(0xFF2A2A3E) : const Color(0xFFF0F0F5),
              child: Center(
                child: CircularProgressIndicator(
                  value: progress.expectedTotalBytes != null
                      ? progress.cumulativeBytesLoaded / progress.expectedTotalBytes!
                      : null,
                  strokeWidth: 2,
                  color: _buttonColor,
                ),
              ),
            );
          },
          errorBuilder: (_, __, ___) => Container(
            height: 100,
            decoration: BoxDecoration(
              color: _isDarkMode ? const Color(0xFF2A2A3E) : const Color(0xFFF5F5F5),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Colors.red.withValues(alpha: 0.2)),
            ),
            child: Center(
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.broken_image, color: Colors.grey[400], size: 20),
                  const SizedBox(width: 8),
                  Text(
                    'Не удалось загрузить',
                    style: GoogleFonts.inter(fontSize: 12, color: Colors.grey[400]),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
    }
    return Container(
      height: 100,
      decoration: BoxDecoration(
        color: _isDarkMode ? const Color(0xFF2A2A3E) : const Color(0xFFF5F5F5),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Center(
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.image, color: Colors.grey[400], size: 20),
            const SizedBox(width: 8),
            Text(
              'Изображение',
              style: GoogleFonts.inter(fontSize: 12, color: Colors.grey[400]),
            ),
          ],
        ),
      ),
    );
  }

  void _showImagePreview(String src) {
    showDialog(
      context: context,
      builder: (ctx) => Dialog(
        backgroundColor: Colors.transparent,
        insetPadding: const EdgeInsets.all(12),
        child: Stack(
          alignment: Alignment.topRight,
          children: [
            InteractiveViewer(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(16),
                child: Image.network(
                  src,
                  fit: BoxFit.contain,
                  loadingBuilder: (_, child, progress) {
                    if (progress == null) return child;
                    return Container(
                      height: 300,
                      color: Colors.black26,
                      child: const Center(child: CircularProgressIndicator(strokeWidth: 2)),
                    );
                  },
                  errorBuilder: (_, __, ___) => Container(
                    height: 200,
                    color: Colors.black26,
                    child: const Center(child: Icon(Icons.broken_image, color: Colors.white54, size: 48)),
                  ),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(8),
              child: IconButton(
                icon: const Icon(Icons.close, color: Colors.white, size: 24),
                onPressed: () => Navigator.pop(ctx),
                splashRadius: 20,
                style: IconButton.styleFrom(
                  backgroundColor: Colors.black38,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  List<InlineSpan> _buildTextSpans(
    String text,
    List<DocumentNote> highlights,
    TextStyle baseStyle, {
    int offset = 0,
  }) {
    final spans = <InlineSpan>[];
    int lastPosition = 0;

    final relevantHighlights = highlights
        .where((n) =>
            n.textPosition != null &&
            n.textPosition! >= offset &&
            n.textPosition! < offset + text.length)
        .toList()
      ..sort((a, b) => (a.textPosition ?? 0).compareTo(b.textPosition ?? 0));

    for (final highlight in relevantHighlights) {
      final start = highlight.textPosition! - offset;
      final end = start + (highlight.selectedText?.length ?? 0);
      if (start < 0 || end > text.length || start >= end) continue;
      if (start > lastPosition) {
        spans.add(TextSpan(text: text.substring(lastPosition, start), style: baseStyle));
      }
      spans.add(
        TextSpan(
          text: text.substring(start, end),
          style: baseStyle.copyWith(
            backgroundColor: _buttonColor.withValues(alpha: 0.15),
          ),
          recognizer: TapGestureRecognizer()..onTap = () => _showNoteDetails(highlight),
        ),
      );
      lastPosition = end;
    }
    if (lastPosition < text.length) {
      spans.add(TextSpan(text: text.substring(lastPosition), style: baseStyle));
    }
    return spans;
  }

  TextStyle _getReadingStyle({double? fontSize, Color? color, double? height}) {
    final style = TextStyle(
      fontSize: fontSize ?? _fontSize,
      color: color ?? _textColor,
      height: height ?? _lineHeight,
      letterSpacing: 0.2,
    );
    switch (_fontFamily) {
      case 'Roboto':
        return GoogleFonts.roboto(textStyle: style);
      case 'Merriweather':
        return GoogleFonts.merriweather(textStyle: style);
      case 'Source Code Pro':
        return GoogleFonts.sourceCodePro(textStyle: style);
      case 'Playfair Display':
        return GoogleFonts.playfairDisplay(textStyle: style);
      default:
        return GoogleFonts.inter(textStyle: style);
    }
  }

  String _createRealFallbackTranslation(String text) {
    return _cleanContentForDisplay(text);
  }

  String _createFallbackTranslation(String text) {
    return '[Локальный перевод не выполнен]\n\n$_currentContent';
  }

  String _stripImagesForApi(String text) {
    return text.replaceAll(RegExp(r'<img\s+[^>]*>', caseSensitive: false), '')
        .replaceAll(RegExp(r'!\[([^\]]*)\]\(([^)]+)\)'), '');
  }

  Future<String?> _polishTranslation(String text) async {
    text = _stripImagesForApi(text);
    if (text.isEmpty || text.length > 8000) return null;
    const apiKey = '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';
    final dio = Dio(
      BaseOptions(
        connectTimeout: const Duration(seconds: 60),
        receiveTimeout: const Duration(seconds: 90),
        headers: {
          'Authorization': 'Bearer $apiKey',
          'Content-Type': 'application/json',
        },
      ),
    );

    const instruction =
        'Сделай этот русский текст связным, литературным и естественным. '
        'Убери повторы, исправь стиль. Верни только исправленный текст:';

    for (final model in [
      'google/flan-t5-large',
      'mistralai/Mistral-7B-Instruct-v0.2',
    ]) {
      try {
        debugPrint('Полировка: пробуем $model');
        final prompt = model == 'mistralai/Mistral-7B-Instruct-v0.2'
            ? '<s>[INST] $instruction\n\n$text [/INST]'
            : '$instruction $text';
        final response = await dio.post(
          'https://api-inference.huggingface.co/models/$model',
          data: {
            'inputs': prompt,
            'parameters': {
              'max_new_tokens': text.length + 300,
              'temperature': 0.3,
              'do_sample': true,
            },
          },
        );

        if (response.statusCode == 200 &&
            response.data is List &&
            response.data.isNotEmpty) {
          String result = '';
          if (response.data[0] is Map) {
            result = response.data[0]['generated_text'] ?? '';
          }
          if (result.isEmpty && response.data[0] is String) {
            result = response.data[0];
          }
          if (result.isNotEmpty) {
            final idx = result.lastIndexOf('[/INST]');
            if (idx != -1) result = result.substring(idx + 7).trim();
            result = result.trim();
            if (result.length >= text.length * 0.3) {
              debugPrint('Полировка: успешно через $model');
              return result;
            }
          }
        } else if (response.statusCode == 503) {
          debugPrint('Полировка: модель $model грузится');
        }
      } catch (e) {
        debugPrint('Полировка: $model error: $e');
      }
    }
    debugPrint('Полировка: AI модели не сработали, применяем локальную');
    return _localPolish(text);
  }

  String _localPolish(String text) {
    text = text.replaceAllMapped(RegExp(r'\b(\w+)\s+\1\b'), (m) => m[1]!);
    text = text.replaceAll(RegExp(r'\n{2,}'), '\n\n');
    text = text.replaceAll(RegExp(r'[ \t]+'), ' ');
    text = text.replaceAll(RegExp(r'^\s+|[ \t]+$', multiLine: true), '');
    final sentences = text.split(RegExp(r'(?<=[.!?])\s+'));
    text = sentences.map((s) {
      s = s.trim();
      if (s.isEmpty) return s;
      return s[0].toUpperCase() + s.substring(1);
    }).join(' ');
    text = text.replaceAllMapped(RegExp(r'\s+([,;:!?])'), (m) => m[1]!);
    text = text.replaceAll(RegExp(r'\b[Ii]\b'), 'Я');
    return text.trim();
  }

  void _toggleTranslation() {
    _translateFullChapter();
  }

  void _onScroll() {
    _lastScrollPosition = _scrollController.offset;
    if (_scrollController.hasClients) {
      final maxScroll = _scrollController.position.maxScrollExtent;
      _scrollProgressNotifier.value = maxScroll > 0
          ? (_scrollController.offset / maxScroll).clamp(0.0, 1.0)
          : 0.0;
    }
    _saveProgressTimer?.cancel();
    _saveProgressTimer = Timer(
      const Duration(seconds: 2),
      _saveReadingProgress,
    );
  }

  Future<void> _saveReadingProgress() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final progress = ReadingProgress(
        documentId: widget.document.id,
        chapterIndex: _currentChapterIndex,
        scrollPosition: _lastScrollPosition,
        timestamp: DateTime.now(),
      );

      final key = 'reading_progress_${widget.document.id}';
      await prefs.setString(key, jsonEncode(progress.toJson()));
    } catch (e) {
      debugPrint('Ошибка сохранения прогресса: $e');
    }
  }

  Future<void> _loadReadingProgress() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final key = 'reading_progress_${widget.document.id}';
      final jsonString = prefs.getString(key);

      if (jsonString != null && jsonString.isNotEmpty) {
        final progress = ReadingProgress.fromJson(jsonDecode(jsonString));
        setState(() {
          _currentChapterIndex = progress.chapterIndex.clamp(
            0,
            _totalChapters - 1,
          );
        });

        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (_scrollController.hasClients) {
            _scrollController.jumpTo(progress.scrollPosition);
          }
        });
      }
    } catch (e) {
      debugPrint('Ошибка загрузки прогресса: $e');
    }
  }

  Future<void> _saveNotes() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final key = 'document_notes_${widget.document.id}';
      final notesJson = _notes.map((note) => note.toJson()).toList();
      await prefs.setString(key, jsonEncode(notesJson));
    } catch (e) {
      debugPrint('Ошибка сохранения заметок: $e');
    }
  }

  Future<void> _loadNotes() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final key = 'document_notes_${widget.document.id}';
      final jsonString = prefs.getString(key);

      if (jsonString != null && jsonString.isNotEmpty) {
        final List<dynamic> notesJson = jsonDecode(jsonString);
        setState(() {
          _notes.clear();
          _notes.addAll(notesJson.map((json) => DocumentNote.fromJson(json)));
        });
      }
    } catch (e) {
      debugPrint('Ошибка загрузки заметок: $e');
    }
  }

  void _addNote({required String text, String? selectedText}) {
    final existingNoteIndex = _notes.indexWhere(
      (note) =>
          note.selectedText == selectedText &&
          note.textPosition == _selectedTextPosition &&
          note.chapterIndex == _currentChapterIndex,
    );

    if (existingNoteIndex != -1) {
      setState(() {
        _notes.removeAt(existingNoteIndex);
      });
      _saveNotes();
      _showSnackbar('Заметка удалена', Colors.red);
      setState(() {
        _selection = null;
        _selectedText = null;
        _selectedTextPosition = null;
      });
      return;
    }

    final newNote = DocumentNote(
      id: DateTime.now().millisecondsSinceEpoch,
      documentId: widget.document.id,
      chapterIndex: _currentChapterIndex,
      text: text,
      selectedText: selectedText,
      textPosition: _selectedTextPosition,
      createdAt: DateTime.now(),
    );

    setState(() {
      _notes.add(newNote);
    });

    _saveNotes();

    _showSnackbar('Заметка сохранена', Colors.green);

    setState(() {
      _selection = null;
      _selectedText = null;
      _selectedTextPosition = null;
    });
  }

  void _jumpToNote(DocumentNote note) {
    if (note.chapterIndex != _currentChapterIndex) {
      setState(() {
        _currentChapterIndex = note.chapterIndex;
        _showTranslation = false;
        _translatedContent = null;
      });
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _scrollController.jumpTo(0);
      });
    }

    if (note.textPosition != null && mounted) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scrollController.hasClients) {
          final estimatedScrollPosition = note.textPosition! * 0.5;
          _scrollController.animateTo(
            estimatedScrollPosition,
            duration: const Duration(milliseconds: 500),
            curve: Curves.easeInOut,
          );
        }
      });
    }
  }

  Future<void> _loadBookmarks() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final key = 'document_bookmarks_${widget.document.id}';
      final jsonString = prefs.getString(key);
      if (jsonString != null && jsonString.isNotEmpty) {
        final List<dynamic> list = jsonDecode(jsonString);
        setState(() {
          _bookmarkedChapters.clear();
          _bookmarkedChapters.addAll(list.map((e) => (e as num).toInt()));
        });
      }
    } catch (e) {
      debugPrint('Ошибка загрузки закладок: $e');
    }
  }

  Future<void> _saveBookmarks() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final key = 'document_bookmarks_${widget.document.id}';
      await prefs.setString(key, jsonEncode(_bookmarkedChapters.toList()));
    } catch (e) {
      debugPrint('Ошибка сохранения закладок: $e');
    }
  }

  void _toggleBookmark() {
    setState(() {
      if (_bookmarkedChapters.contains(_currentChapterIndex)) {
        _bookmarkedChapters.remove(_currentChapterIndex);
        _showSnackbar('Закладка удалена', Colors.red);
      } else {
        _bookmarkedChapters.add(_currentChapterIndex);
        _showSnackbar('Глава добавлена в закладки', Colors.green);
      }
    });
    _saveBookmarks();
  }

  Widget _buildBookmarkButton() {
    final isBookmarked = _bookmarkedChapters.contains(_currentChapterIndex);
    return IconButton(
      icon: Icon(
        isBookmarked ? Icons.bookmark : Icons.bookmark_border,
        color: isBookmarked ? _buttonColor : _textColor.withValues(alpha: 0.6),
        size: 20,
      ),
      onPressed: _toggleBookmark,
      tooltip: isBookmarked ? 'Удалить закладку' : 'Добавить закладку',
      splashRadius: 18,
      constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
      padding: EdgeInsets.zero,
    );
  }

  Widget _buildFontSizeButton(int direction, IconData icon, String tooltip) {
    return IconButton(
      icon: Icon(icon, size: 18, color: _buttonColor),
      onPressed: () {
        setState(() {
          final newSize = _fontSize + direction;
          if (newSize >= 12 && newSize <= 28) {
            _fontSize = newSize;
          }
        });
      },
      tooltip: tooltip,
      splashRadius: 16,
      constraints: const BoxConstraints(minWidth: 30, minHeight: 30),
      padding: EdgeInsets.zero,
    );
  }

  Widget _buildContent() {
    final String rawContent;

    if (_showTranslation) {
      if (_translatedContent != null && _translatedContent!.isNotEmpty) {
        rawContent = _translatedContent!;
      } else if (_isTranslating) {
        rawContent =
            'Загрузка перевода...\n\n${_currentContent.substring(0, min(200, _currentContent.length))}';
      } else {
        rawContent = _createFallbackTranslation(_currentContent);
      }
    } else {
      rawContent = _currentContent;
    }
    final displayContent = _cleanContentForDisplay(rawContent);

    final currentChapterNotes = _notes
        .where((note) => note.chapterIndex == _currentChapterIndex)
        .toList();

    final highlights = currentChapterNotes
        .where((note) => note.textPosition != null)
        .toList();

    highlights.sort(
      (a, b) => (a.textPosition ?? 0).compareTo(b.textPosition ?? 0),
    );

    final baseStyle = _getReadingStyle().copyWith(
      height: _lineHeight,
    );

    final imageSpans = _buildImageInlineSpans(displayContent, highlights, baseStyle);

    return Container(
      color: _backgroundColor,
      child: Stack(
        children: [
          SingleChildScrollView(
            key: _contentKey,
            controller: _scrollController,
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _buildChapterHeader(currentChapterNotes),
                const SizedBox(height: 8),
                SelectableText.rich(
                  TextSpan(children: imageSpans),
                  textAlign: TextAlign.justify,
                  selectionColor: _buttonColor.withValues(alpha: 0.25),
                  onSelectionChanged: (selection, cause) {
                    if (selection.isValid) {
                      final selected = selection.textInside(displayContent);
                      if (selected.isNotEmpty) {
                        setState(() {
                          _selection = selection;
                          _selectedText = selected;
                          _selectedTextPosition = selection.start;
                        });
                      }
                    }
                  },
                ),
                const SizedBox(height: 32),
                _buildChapterNotes(currentChapterNotes),
                const SizedBox(height: 80),
              ],
            ),
          ),
          if (_selectedText != null && _selectedText!.isNotEmpty)
            Positioned(
              bottom: 24,
              left: 0,
              right: 0,
              child: _buildSelectionPanel(),
            ),
          if (_isTranslating)
            Positioned.fill(
              child: Container(
                color: Colors.black.withValues(alpha: 0.7),
                child: Center(child: _buildTranslationProgressOverlay()),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildTranslationProgressOverlay() {
    return Container(
      padding: const EdgeInsets.all(24),
      margin: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: _isDarkMode ? const Color(0xFF1E1E2E) : Colors.white,
        borderRadius: BorderRadius.circular(24),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.3),
            blurRadius: 30,
            spreadRadius: 5,
          ),
        ],
      ),
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.7,
        ),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Stack(
                alignment: Alignment.center,
                children: [
                  SizedBox(
                    width: 120,
                    height: 120,
                    child: CircularProgressIndicator(
                      value: _translationProgress / 100,
                      strokeWidth: 8,
                      backgroundColor: _isDarkMode
                          ? Colors.grey[700]
                          : Colors.grey[200],
                      valueColor: AlwaysStoppedAnimation<Color>(_buttonColor),
                    ),
                  ),
                  Icon(Icons.translate, size: 40, color: _buttonColor),
                ],
              ),
              const SizedBox(height: 24),
              Text(
                _translationProgress >= 100 && _totalChunks > 0
                    ? 'Полировка текста'
                    : 'Перевод главы',
                style: GoogleFonts.inter(
                  fontSize: 22,
                  fontWeight: FontWeight.w700,
                  color: _isDarkMode ? Colors.white : Colors.black87,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                '«$_currentTitle»',
                style: GoogleFonts.inter(
                  fontSize: 16,
                  color: _isDarkMode ? Colors.grey[400] : Colors.grey[700],
                  fontStyle: FontStyle.italic,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: LinearProgressIndicator(
                  value: _translationProgress / 100,
                  backgroundColor: _isDarkMode
                      ? Colors.grey[700]
                      : Colors.grey[200],
                  valueColor: AlwaysStoppedAnimation<Color>(Colors.green),
                  minHeight: 8,
                ),
              ),
              const SizedBox(height: 12),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    'Прогресс:',
                    style: GoogleFonts.inter(
                      fontSize: 14,
                      color: _isDarkMode ? Colors.grey[400] : Colors.grey[700],
                    ),
                  ),
                  Text(
                    '$_translationProgress%',
                    style: GoogleFonts.inter(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                      color: _buttonColor,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              if (_translationProgress >= 100 && _totalChunks > 0)
                Text(
                  'Полируем, чтобы звучало естественно...',
                  style: GoogleFonts.inter(
                    fontSize: 13,
                    color: _isDarkMode ? Colors.grey[400] : Colors.grey[600],
                    fontStyle: FontStyle.italic,
                  ),
                )
              else
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      'Чанк:',
                      style: GoogleFonts.inter(
                        fontSize: 14,
                        color: _isDarkMode
                            ? Colors.grey[400]
                            : Colors.grey[700],
                      ),
                    ),
                    Text(
                      '$_currentChunk/$_totalChunks',
                      style: GoogleFonts.inter(
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                        color: _isDarkMode
                            ? Colors.grey[300]
                            : Colors.grey[800],
                      ),
                    ),
                  ],
                ),
              const SizedBox(height: 24),
              SizedBox(
                height: 30,
                child: Center(
                  child: SizedBox(
                    width: 60,
                    height: 20,
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        LoadingDot(delay: 0),
                        LoadingDot(delay: 200),
                        LoadingDot(delay: 400),
                      ],
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Text(
                _getProgressMessage(),
                style: GoogleFonts.inter(
                  fontSize: 14,
                  color: _isDarkMode ? Colors.grey[500] : Colors.grey[600],
                  fontStyle: FontStyle.italic,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 20),
              OutlinedButton(
                onPressed: () {
                  setState(() {
                    _isTranslating = false;
                    _showTranslation = false;
                  });
                },
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.red,
                  side: const BorderSide(color: Colors.red),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 24,
                    vertical: 12,
                  ),
                ),
                child: const Text('Остановить перевод'),
              ),
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }

  String _getProgressMessage() {
    if (_translationProgress < 30) {
      return 'Подготовка текста...';
    } else if (_translationProgress < 60) {
      return 'Переводим первые части...';
    } else if (_translationProgress < 90) {
      return 'Завершаем перевод...';
    } else {
      return 'Собираем результат...';
    }
  }

  Widget _buildChapterHeader(List<DocumentNote> chapterNotes) {
    return Container(
      margin: const EdgeInsets.only(bottom: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.only(left: 14),
            decoration: BoxDecoration(
              border: Border(left: BorderSide(color: _buttonColor, width: 4)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      'Глава ${_currentChapterIndex + 1}',
                      style: GoogleFonts.inter(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: _buttonColor,
                        letterSpacing: 0.5,
                      ),
                    ),
                    if (_bookmarkedChapters.contains(_currentChapterIndex)) ...[
                      const SizedBox(width: 6),
                      Icon(Icons.bookmark, size: 12, color: _buttonColor),
                    ],
                  ],
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        _currentTitle,
                        style: GoogleFonts.inter(
                          fontSize: _fontSize + 8,
                          fontWeight: FontWeight.w700,
                          color: _textColor,
                          height: 1.3,
                          letterSpacing: -0.3,
                        ),
                      ),
                    ),
                    if (chapterNotes.isNotEmpty)
                      IconButton(
                        icon: _buildBadgeIcon(
                          Icons.note,
                          chapterNotes.length,
                          color: _buttonColor,
                        ),
                        onPressed: () => _showChapterNotesDialog(chapterNotes),
                        tooltip: 'Заметки к главе',
                      ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 10),
          Container(
            height: 1,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  _buttonColor.withValues(alpha: 0.4),
                  _buttonColor.withValues(alpha: 0.0),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBadgeIcon(IconData icon, int count, {Color? color}) {
    return Stack(
      children: [
        Icon(icon, color: color ?? _textColor),
        if (count > 0)
          Positioned(
            right: 0,
            top: 0,
            child: Container(
              padding: const EdgeInsets.all(1),
              decoration: BoxDecoration(
                color: Colors.red,
                borderRadius: BorderRadius.circular(6),
              ),
              constraints: const BoxConstraints(minWidth: 12, minHeight: 12),
              child: Text(
                count > 9 ? '9+' : '$count',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 8,
                  fontWeight: FontWeight.bold,
                ),
                textAlign: TextAlign.center,
              ),
            ),
          ),
      ],
    );
  }

  Widget _buildChapterNotes(List<DocumentNote> chapterNotes) {
    if (chapterNotes.isEmpty) return const SizedBox();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 20),
        Row(
          children: [
            Icon(
              Icons.note,
              size: 18,
              color: _buttonColor.withValues(alpha: 0.7),
            ),
            const SizedBox(width: 8),
            Text(
              'Заметки к главе',
              style: GoogleFonts.inter(
                fontSize: _fontSize + 2,
                fontWeight: FontWeight.w600,
                color: _textColor,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        ...chapterNotes.map((note) => _buildNoteCard(note)),
      ],
    );
  }

  Widget _buildNoteCard(DocumentNote note) {
    final noteColor = _buttonColor;
    final chapters = widget.document.chapters.isNotEmpty
        ? widget.document.chapters
        : _autoChapters;
    final chapterTitle = note.chapterIndex < chapters.length
        ? (chapters[note.chapterIndex]['title']?.toString() ??
              'Глава ${note.chapterIndex + 1}')
        : 'Глава ${note.chapterIndex + 1}';
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      elevation: _isDarkMode ? 0 : 1,
      color: _isDarkMode ? const Color(0xFF2A2A3E) : Colors.white,
      shadowColor: Colors.black.withValues(alpha: 0.08),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: noteColor.withValues(alpha: 0.3), width: 0.5),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: () => _showNoteDetails(note),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 28,
                    height: 28,
                    decoration: BoxDecoration(
                      color: noteColor.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Icon(Icons.note, size: 14, color: noteColor),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          chapterTitle,
                          style: GoogleFonts.inter(
                            fontWeight: FontWeight.w600,
                            color: _textColor,
                            fontSize: 13,
                          ),
                        ),
                        Text(
                          _formatDate(note.createdAt),
                          style: GoogleFonts.inter(
                            color: _textColor.withValues(alpha: 0.4),
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      SizedBox(
                        width: 28,
                        height: 28,
                        child: IconButton(
                          padding: EdgeInsets.zero,
                          icon: Icon(Icons.visibility, size: 14),
                          onPressed: () => _showNoteDetails(note),
                          tooltip: 'Просмотреть заметку',
                          color: _textColor.withValues(alpha: 0.5),
                        ),
                      ),
                      SizedBox(
                        width: 28,
                        height: 28,
                        child: IconButton(
                          padding: EdgeInsets.zero,
                          icon: Icon(Icons.delete_outline, size: 14),
                          onPressed: () => _confirmDeleteNote(note),
                          tooltip: 'Удалить заметку',
                          color: Colors.red.withValues(alpha: 0.6),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
              if (note.selectedText != null && note.selectedText!.isNotEmpty) ...[
                const SizedBox(height: 10),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: noteColor.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(
                      color: noteColor.withValues(alpha: 0.15),
                    ),
                  ),
                  child: Text(
                    note.selectedText!,
                    style: GoogleFonts.inter(
                      fontStyle: FontStyle.italic,
                      fontSize: 13,
                      color: _textColor.withValues(alpha: 0.75),
                      height: 1.4,
                    ),
                  ),
                ),
              ],
              if (note.text.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(
                  note.text,
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                  style: GoogleFonts.inter(
                    color: _textColor,
                    fontSize: 14,
                    height: 1.5,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSelectionPanel() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: Material(
        elevation: 12,
        borderRadius: BorderRadius.circular(16),
        shadowColor: Colors.black.withValues(alpha: 0.2),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
          decoration: BoxDecoration(
            color: _isDarkMode ? const Color(0xFF2A2A3E) : Colors.white,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: _isDarkMode
                  ? Colors.white.withValues(alpha: 0.08)
                  : Colors.grey.withValues(alpha: 0.15),
            ),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              _buildSelectionButton(
                icon: Icons.copy,
                tooltip: 'Копировать',
                onTap: () => _copySelectedText(_selectedText!),
              ),
              _buildSelectionButton(
                icon: Icons.note_add,
                tooltip: 'Добавить заметку',
                onTap: () => _showAddNoteForSelectionDialog(_selectedText!),
              ),
              _buildSelectionButton(
                icon: Icons.close,
                tooltip: 'Закрыть',
                onTap: () {
                  setState(() {
                    _selection = null;
                    _selectedText = null;
                    _selectedTextPosition = null;
                  });
                },
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSelectionButton({
    required IconData icon,
    required String tooltip,
    required VoidCallback onTap,
    Color? color,
  }) {
    return IconButton(
      icon: Icon(icon, size: 20),
      onPressed: onTap,
      tooltip: tooltip,
      color: color ?? _textColor,
      splashRadius: 20,
      style: IconButton.styleFrom(
        backgroundColor: Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    );
  }

  void _showAddNoteForSelectionDialog(String selectedText) {
    final TextEditingController controller = TextEditingController();

    showDialog(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) {
          return AlertDialog(
            title: Text(
              'Добавить заметку',
              style: GoogleFonts.inter(fontWeight: FontWeight.w600),
            ),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: _buttonColor.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      selectedText,
                      style: GoogleFonts.inter(
                        fontStyle: FontStyle.italic,
                        color: _textColor,
                        fontSize: 14,
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: controller,
                    autofocus: true,
                    maxLines: 4,
                    decoration: InputDecoration(
                      hintText: 'Введите вашу заметку...',
                      hintStyle: GoogleFonts.inter(color: Colors.grey[400]),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: BorderSide(color: Colors.grey[300]!),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: BorderSide(color: _buttonColor),
                      ),
                      filled: true,
                      fillColor: _isDarkMode
                          ? const Color(0xFF2A2A3E)
                          : Colors.grey[50],
                    ),
                    style: GoogleFonts.inter(color: _textColor),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: Text(
                  'Отмена',
                  style: GoogleFonts.inter(color: Colors.grey[600]),
                ),
              ),
              TextButton(
                onPressed: () {
                  if (controller.text.trim().isNotEmpty) {
                    _addNote(
                      text: controller.text.trim(),
                      selectedText: selectedText,
                    );
                  }
                  Navigator.pop(context);
                },
                child: Text(
                  'Сохранить',
                  style: GoogleFonts.inter(
                    color: _buttonColor,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  void _showChapterNotesDialog(List<DocumentNote> notes) {
    showDialog(
      context: context,
      builder: (ctx) => Dialog(
        backgroundColor: _isDarkMode ? const Color(0xFF1E1E2E) : Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(Icons.note, color: _buttonColor, size: 20),
                  const SizedBox(width: 10),
                  Text(
                    'Заметки к главе',
                    style: GoogleFonts.inter(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: _textColor,
                    ),
                  ),
                  const Spacer(),
                  IconButton(
                    icon: Icon(Icons.close, size: 18, color: _textColor.withValues(alpha: 0.5)),
                    onPressed: () => Navigator.pop(ctx),
                    splashRadius: 18,
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Flexible(
                child: ListView.builder(
                  shrinkWrap: true,
                  itemCount: notes.length,
                  itemBuilder: (_, i) => Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: _buildNoteCard(notes[i]),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showNoteDetails(DocumentNote note) {
    showDialog(
      context: context,
      builder: (ctx) => Dialog(
        backgroundColor: _isDarkMode ? const Color(0xFF1E1E2E) : Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 32, height: 32,
                    decoration: BoxDecoration(
                      color: _buttonColor.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Icon(Icons.note, size: 16, color: _buttonColor),
                  ),
                  const SizedBox(width: 10),
                  Text(
                    'Заметка',
                    style: GoogleFonts.inter(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: _textColor,
                    ),
                  ),
                  const Spacer(),
                  Text(
                    _formatDate(note.createdAt),
                    style: GoogleFonts.inter(
                      fontSize: 12,
                      color: _textColor.withValues(alpha: 0.4),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              if (note.selectedText != null && note.selectedText!.isNotEmpty) ...[
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: _buttonColor.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: _buttonColor.withValues(alpha: 0.15)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Выделенный текст',
                        style: GoogleFonts.inter(
                          fontSize: 10,
                          fontWeight: FontWeight.w600,
                          color: _buttonColor,
                          letterSpacing: 0.5,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        note.selectedText!,
                        style: GoogleFonts.inter(
                          fontStyle: FontStyle.italic,
                          fontSize: 14,
                          color: _textColor.withValues(alpha: 0.8),
                          height: 1.4,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
              ],
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: _isDarkMode ? const Color(0xFF2A2A3E) : const Color(0xFFF8F8FC),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  note.text,
                  style: GoogleFonts.inter(
                    fontSize: 15,
                    color: _textColor,
                    height: 1.5,
                  ),
                ),
              ),
              const SizedBox(height: 20),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () => Navigator.pop(ctx),
                      icon: const Icon(Icons.close, size: 16),
                      label: Text('Закрыть', style: GoogleFonts.inter()),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: _textColor.withValues(alpha: 0.6),
                        side: BorderSide(color: _textColor.withValues(alpha: 0.15)),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: ElevatedButton.icon(
                      onPressed: () {
                        Navigator.pop(ctx);
                        _jumpToNote(note);
                      },
                      icon: const Icon(Icons.open_in_new, size: 16),
                      label: Text('Перейти', style: GoogleFonts.inter()),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: _buttonColor,
                        foregroundColor: Colors.white,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                        elevation: 0,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              SizedBox(
                width: double.infinity,
                child: TextButton.icon(
                  onPressed: () {
                    Navigator.pop(ctx);
                    _confirmDeleteNote(note);
                  },
                  icon: Icon(Icons.delete_outline, size: 16, color: Colors.red.withValues(alpha: 0.7)),
                  label: Text(
                    'Удалить заметку',
                    style: GoogleFonts.inter(color: Colors.red.withValues(alpha: 0.7)),
                  ),
                  style: TextButton.styleFrom(
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showReadingSettings() {
    final fontFamilies = ['Inter', 'Roboto', 'Merriweather', 'Playfair Display', 'Source Code Pro'];
    final sizePresets = [14, 16, 18, 20, 22, 24, 28];
    final lineHeightPresets = [1.2, 1.5, 1.8, 2.0, 2.2];
    final themes = [
      ('Светлая', Colors.white, Colors.black87, _buttonColor),
      ('Темная', const Color(0xFF1A1A2E), const Color(0xFFE0E0E0), _buttonColor),
      ('Сепия', const Color(0xFFF8E9D0), const Color(0xFF5C4636), const Color(0xFF8B4513)),
      ('Ночная', const Color(0xFF0A0A0A), const Color(0xFFE0E0E0), const Color(0xFF4A90E2)),
      ('Бумага', const Color(0xFFF5F5DC), const Color(0xFF3E2723), const Color(0xFF795548)),
    ];

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setModalState) {
          return Container(
            height: MediaQuery.of(ctx).size.height * 0.75,
            decoration: BoxDecoration(
              color: _isDarkMode ? const Color(0xFF1E1E2E) : Colors.white,
              borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
            ),
            child: Column(
              children: [
                Container(
                  padding: const EdgeInsets.fromLTRB(20, 16, 12, 12),
                  child: Row(
                    children: [
                      Icon(Icons.tune, size: 20, color: _buttonColor),
                      const SizedBox(width: 10),
                      Text(
                        'Настройки чтения',
                        style: GoogleFonts.inter(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                          color: _textColor,
                        ),
                      ),
                      const Spacer(),
                      IconButton(
                        icon: Icon(Icons.close, size: 20, color: _textColor.withValues(alpha: 0.5)),
                        onPressed: () => Navigator.pop(ctx),
                        splashRadius: 20,
                      ),
                    ],
                  ),
                ),
                Divider(height: 1, color: _textColor.withValues(alpha: 0.08)),
                Expanded(
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
                    children: [
                      _buildSettingsSection(
                        'Шрифт',
                        Icons.font_download_outlined,
                        SizedBox(
                          height: 70,
                          child: ListView.separated(
                            scrollDirection: Axis.horizontal,
                            itemCount: fontFamilies.length,
                            separatorBuilder: (_, __) => const SizedBox(width: 10),
                            itemBuilder: (_, i) {
                              final name = fontFamilies[i];
                              final selected = _fontFamily == name;
                              return GestureDetector(
                                onTap: () {
                                  setModalState(() {
                                    setState(() {
                                      _fontFamily = name;
                                    });
                                  });
                                },
                                child: Container(
                                  width: 110,
                                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                                  decoration: BoxDecoration(
                                    color: selected ? _buttonColor.withValues(alpha: 0.12) : _textColor.withValues(alpha: 0.04),
                                    borderRadius: BorderRadius.circular(12),
                                    border: Border.all(
                                      color: selected ? _buttonColor.withValues(alpha: 0.4) : _textColor.withValues(alpha: 0.08),
                                    ),
                                  ),
                                  child: Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        name,
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: GoogleFonts.inter(
                                          fontSize: 12,
                                          fontWeight: FontWeight.w600,
                                          color: selected ? _buttonColor : _textColor,
                                        ),
                                      ),
                                      const SizedBox(height: 2),
                                      Text(
                                        'AaBb',
                                        style: GoogleFonts.inter(
                                          fontSize: 18,
                                          color: selected ? _buttonColor : _textColor.withValues(alpha: 0.4),
                                          fontWeight: FontWeight.w500,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              );
                            },
                          ),
                        ),
                      ),
                      const SizedBox(height: 20),
                      _buildSettingsSection(
                        'Размер текста',
                        Icons.text_fields,
                        Column(
                          children: [
                            Row(
                              children: [
                                IconButton(
                                  icon: Icon(Icons.remove_circle_outline, color: _buttonColor),
                                  onPressed: () {
                                    setModalState(() {
                                      if (_fontSize > 12) setState(() => _fontSize--);
                                    });
                                  },
                                  splashRadius: 18,
                                ),
                                Expanded(
                                  child: Slider(
                                    value: _fontSize,
                                    min: 12,
                                    max: 28,
                                    divisions: 32,
                                    activeColor: _buttonColor,
                                    inactiveColor: _textColor.withValues(alpha: 0.12),
                                    label: '${_fontSize.toInt()}',
                                    onChanged: (v) {
                                      setModalState(() {
                                        setState(() => _fontSize = v.roundToDouble());
                                      });
                                    },
                                  ),
                                ),
                                IconButton(
                                  icon: Icon(Icons.add_circle_outline, color: _buttonColor),
                                  onPressed: () {
                                    setModalState(() {
                                      if (_fontSize < 28) setState(() => _fontSize++);
                                    });
                                  },
                                  splashRadius: 18,
                                ),
                              ],
                            ),
                            const SizedBox(height: 4),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                              children: sizePresets.map((s) {
                                final isActive = _fontSize.round() == s;
                                return GestureDetector(
                                  onTap: () {
                                    setModalState(() {
                                      setState(() => _fontSize = s.toDouble());
                                    });
                                  },
                                  child: Container(
                                    width: 36,
                                    height: 32,
                                    alignment: Alignment.center,
                                    decoration: BoxDecoration(
                                      color: isActive ? _buttonColor.withValues(alpha: 0.12) : null,
                                      borderRadius: BorderRadius.circular(8),
                                    ),
                                    child: Text(
                                      '$s',
                                      style: GoogleFonts.inter(
                                        fontSize: 11,
                                        fontWeight: isActive ? FontWeight.w700 : FontWeight.w400,
                                        color: isActive ? _buttonColor : _textColor.withValues(alpha: 0.5),
                                      ),
                                    ),
                                  ),
                                );
                              }).toList(),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 20),
                      _buildSettingsSection(
                        'Межстрочный интервал',
                        Icons.format_line_spacing,
                        Row(
                          children: lineHeightPresets.map((lh) {
                            final isActive = _lineHeight == lh;
                            return Expanded(
                              child: Padding(
                                padding: const EdgeInsets.symmetric(horizontal: 3),
                                child: GestureDetector(
                                  onTap: () {
                                    setModalState(() {
                                      setState(() => _lineHeight = lh);
                                    });
                                  },
                                  child: Container(
                                    padding: const EdgeInsets.symmetric(vertical: 10),
                                    alignment: Alignment.center,
                                    decoration: BoxDecoration(
                                      color: isActive ? _buttonColor.withValues(alpha: 0.12) : _textColor.withValues(alpha: 0.04),
                                      borderRadius: BorderRadius.circular(10),
                                      border: Border.all(
                                        color: isActive ? _buttonColor.withValues(alpha: 0.4) : _textColor.withValues(alpha: 0.08),
                                      ),
                                    ),
                                    child: Text(
                                      lh == 1.2 ? 'Плотный' :
                                      lh == 1.5 ? 'Средний' :
                                      lh == 1.8 ? 'Обычный' :
                                      lh == 2.0 ? 'Просторный' : 'Широкий',
                                      style: GoogleFonts.inter(
                                        fontSize: 10,
                                        fontWeight: FontWeight.w600,
                                        color: isActive ? _buttonColor : _textColor.withValues(alpha: 0.6),
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            );
                          }).toList(),
                        ),
                      ),
                      const SizedBox(height: 20),
                      _buildSettingsSection(
                        'Тема оформления',
                        Icons.palette_outlined,
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                          children: themes.map((t) {
                            final name = t.$1;
                            final bg = t.$2;
                            final fg = t.$3;
                            final accent = t.$4;
                            final isActive = _backgroundColor == bg;
                            return GestureDetector(
                              onTap: () {
                                setModalState(() {
                                  setState(() {
                                    _isDarkMode = bg.computeLuminance() < 0.5;
                                    _backgroundColor = bg;
                                    _textColor = fg;
                                    _buttonColor = accent;
                                  });
                                });
                              },
                              child: Column(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Container(
                                    width: 44,
                                    height: 44,
                                    decoration: BoxDecoration(
                                      color: bg,
                                      shape: BoxShape.circle,
                                      border: Border.all(
                                        color: isActive ? accent : bg.computeLuminance() < 0.5 ? Colors.white.withValues(alpha: 0.15) : Colors.black.withValues(alpha: 0.1),
                                        width: isActive ? 3 : 1,
                                      ),
                                      boxShadow: isActive ? [
                                        BoxShadow(color: accent.withValues(alpha: 0.3), blurRadius: 8),
                                      ] : null,
                                    ),
                                    child: isActive
                                        ? Icon(Icons.check, size: 18, color: fg)
                                        : null,
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    name,
                                    style: GoogleFonts.inter(
                                      fontSize: 9,
                                      color: _textColor.withValues(alpha: 0.5),
                                    ),
                                  ),
                                ],
                              ),
                            );
                          }).toList(),
                        ),
                      ),
                      const SizedBox(height: 20),
                      Container(
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: _backgroundColor,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: _textColor.withValues(alpha: 0.08)),
                        ),
                        child: Text(
                          'Пример текста с текущими настройками. '
                          'Шрифт $_fontFamily, размер $_fontSize, '
                          'интервал $_lineHeight. Здесь отображается, '
                          'как будет выглядеть ваш текст для чтения.',
                          style: _getReadingStyle().copyWith(fontSize: _fontSize - 2),
                          textAlign: TextAlign.justify,
                        ),
                      ),
                      const SizedBox(height: 24),
                      SizedBox(
                        width: double.infinity,
                        child: ElevatedButton(
                          onPressed: () => Navigator.pop(ctx),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: _buttonColor,
                            foregroundColor: Colors.white,
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                            padding: const EdgeInsets.symmetric(vertical: 14),
                            elevation: 0,
                          ),
                          child: Text(
                            'Готово',
                            style: GoogleFonts.inter(fontWeight: FontWeight.w600, fontSize: 15),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildSettingsSection(String title, IconData icon, Widget child) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(icon, size: 16, color: _textColor.withValues(alpha: 0.5)),
            const SizedBox(width: 6),
            Text(
              title,
              style: GoogleFonts.inter(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: _textColor.withValues(alpha: 0.7),
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        child,
      ],
    );
  }

  void _copySelectedText(String text) {
    Clipboard.setData(ClipboardData(text: text));
    _showSnackbar(
      'Скопировано: ${text.length > 20 ? '${text.substring(0, 20)}...' : text}',
      Colors.blue,
    );
    setState(() {
      _selection = null;
      _selectedText = null;
      _selectedTextPosition = null;
    });
  }

  void _showAllNotesDialog() {
    showDialog(
      context: context,
      builder: (ctx) => Dialog(
        backgroundColor: _isDarkMode ? const Color(0xFF1E1E2E) : Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(Icons.notes, color: _buttonColor, size: 20),
                  const SizedBox(width: 10),
                  Text(
                    'Все заметки',
                    style: GoogleFonts.inter(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: _textColor,
                    ),
                  ),
                  if (_notes.isNotEmpty) ...[
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                      decoration: BoxDecoration(
                        color: _buttonColor.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text(
                        '${_notes.length}',
                        style: GoogleFonts.inter(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: _buttonColor,
                        ),
                      ),
                    ),
                  ],
                  const Spacer(),
                  IconButton(
                    icon: Icon(Icons.close, size: 18, color: _textColor.withValues(alpha: 0.5)),
                    onPressed: () => Navigator.pop(ctx),
                    splashRadius: 18,
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              if (_notes.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 40),
                  child: Center(
                    child: Column(
                      children: [
                        Icon(Icons.note_add, size: 40, color: Colors.grey[300]),
                        const SizedBox(height: 12),
                        Text(
                          'Нет заметок',
                          style: GoogleFonts.inter(
                            fontSize: 16,
                            color: Colors.grey[400],
                          ),
                        ),
                        Text(
                          'Выделите текст и добавьте заметку',
                          style: GoogleFonts.inter(
                            fontSize: 13,
                            color: Colors.grey[400],
                          ),
                        ),
                      ],
                    ),
                  ),
                )
              else
                Flexible(
                  child: () {
                    final chapters = widget.document.chapters.isNotEmpty
                        ? widget.document.chapters
                        : _autoChapters;
                    final grouped = <int, List<DocumentNote>>{};
                    for (final note in _notes) {
                      grouped.putIfAbsent(note.chapterIndex, () => []).add(note);
                    }
                    final sortedKeys = grouped.keys.toList()..sort();
                    return ListView(
                      shrinkWrap: true,
                      children: sortedKeys.expand((chIdx) {
                        final title = chIdx < chapters.length
                            ? (chapters[chIdx]['title']?.toString() ?? 'Глава ${chIdx + 1}')
                            : 'Глава ${chIdx + 1}';
                        final notes = grouped[chIdx]!;
                        return [
                          if (sortedKeys.length > 1)
                            Padding(
                              padding: const EdgeInsets.only(top: 4, bottom: 8),
                              child: Row(
                                children: [
                                  Container(
                                    width: 3,
                                    height: 14,
                                    decoration: BoxDecoration(
                                      color: _buttonColor,
                                      borderRadius: BorderRadius.circular(2),
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  Text(
                                    title,
                                    style: GoogleFonts.inter(
                                      fontSize: 12,
                                      fontWeight: FontWeight.w600,
                                      color: _textColor.withValues(alpha: 0.6),
                                    ),
                                  ),
                                  const SizedBox(width: 6),
                                  Text(
                                    '${notes.length}',
                                    style: GoogleFonts.inter(
                                      fontSize: 11,
                                      color: _textColor.withValues(alpha: 0.35),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ...notes.map((n) => Padding(
                            padding: const EdgeInsets.only(bottom: 10),
                            child: _buildNoteCard(n),
                          )),
                        ];
                      }).toList(),
                    );
                  }(),
                ),
            ],
          ),
        ),
      ),
    );
  }

  void _confirmDeleteNote(DocumentNote note) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Text('Удалить заметку?', style: GoogleFonts.inter(fontWeight: FontWeight.w600)),
        content: Text(
          'Это действие нельзя отменить.',
          style: GoogleFonts.inter(fontSize: 14, color: Colors.grey[600]),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text('Отмена', style: GoogleFonts.inter(color: Colors.grey[600])),
          ),
          TextButton(
            onPressed: () {
              setState(() {
                _notes.remove(note);
              });
              _saveNotes();
              Navigator.pop(ctx);
              _showSnackbar('Заметка удалена', Colors.red);
            },
            child: Text('Удалить', style: GoogleFonts.inter(color: Colors.red)),
          ),
        ],
      ),
    );
  }

  void _showSnackbar(String message, Color color) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message, style: GoogleFonts.inter()),
        backgroundColor: color,
        duration: const Duration(seconds: 2),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  String _formatDate(DateTime date) {
    final now = DateTime.now();
    final difference = now.difference(date);

    if (difference.inDays == 0) return 'сегодня';
    if (difference.inDays == 1) return 'вчера';
    if (difference.inDays < 7) return '${difference.inDays} дн. назад';
    if (difference.inDays < 30) return '${difference.inDays ~/ 7} нед. назад';
    return '${difference.inDays ~/ 30} мес. назад';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _backgroundColor,
      appBar: AppBar(
        backgroundColor: _backgroundColor,
        elevation: 0,
        scrolledUnderElevation: 0,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.document.title,
              style: GoogleFonts.inter(
                fontSize: 16,
                color: _textColor,
                fontWeight: FontWeight.w600,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            if (_totalChapters > 1)
              Text(
                _currentTitle,
                style: GoogleFonts.inter(
                  fontSize: 11,
                  color: _textColor.withValues(alpha: 0.5),
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
          ],
        ),
        leading: IconButton(
          icon: Icon(Icons.arrow_back, color: _textColor),
          onPressed: () {
            _saveReadingProgress();
            Navigator.pop(context);
          },
        ),
        actions: [
          if (_notes.isNotEmpty)
            IconButton(
              icon: _buildBadgeIcon(
                Icons.note,
                _notes.length,
                color: _buttonColor,
              ),
              onPressed: _showAllNotesDialog,
              tooltip: 'Заметки',
            ),
          PopupMenuButton<String>(
            icon: Icon(Icons.more_vert, color: _textColor),
            color: _isDarkMode ? const Color(0xFF2A2A3E) : Colors.white,
            elevation: 4,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
            onSelected: (value) {
              if (value == 'settings') _showReadingSettings();
              if (value == 'notes') _showAllNotesDialog();
            },
            itemBuilder: (context) => [
              PopupMenuItem(
                value: 'settings',
                child: Row(
                  children: [
                    Container(
                      width: 32, height: 32,
                      decoration: BoxDecoration(
                        color: _buttonColor.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Icon(Icons.tune, size: 18, color: _buttonColor),
                    ),
                    const SizedBox(width: 10),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text('Настройки чтения', style: GoogleFonts.inter(color: _textColor, fontWeight: FontWeight.w500)),
                        Text('Шрифт, размер, тема', style: GoogleFonts.inter(color: _textColor.withValues(alpha: 0.4), fontSize: 11)),
                      ],
                    ),
                  ],
                ),
              ),
              PopupMenuItem(
                value: 'notes',
                child: Row(
                  children: [
                    Container(
                      width: 32, height: 32,
                      decoration: BoxDecoration(
                        color: Colors.amber.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Icon(Icons.note, size: 18, color: Colors.amber.shade700),
                    ),
                    const SizedBox(width: 10),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text('Заметки', style: GoogleFonts.inter(color: _textColor, fontWeight: FontWeight.w500)),
                        if (_notes.isNotEmpty)
                          Text('${_notes.length} шт.', style: GoogleFonts.inter(color: _textColor.withValues(alpha: 0.4), fontSize: 11)),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
      body: Column(
        children: [
          ValueListenableBuilder<double>(
            valueListenable: _scrollProgressNotifier,
            builder: (context, value, child) {
              return LinearProgressIndicator(
                value: value,
                backgroundColor: (_isDarkMode ? Colors.white : Colors.black)
                    .withValues(alpha: 0.06),
                valueColor: AlwaysStoppedAnimation<Color>(
                  _buttonColor.withValues(alpha: 0.5),
                ),
                minHeight: 2,
              );
            },
          ),
          _buildToolbar(),
          Expanded(child: _buildContent()),
          if (_totalChapters > 1) _buildNavigationPanel(),
        ],
      ),
    );
  }

  Widget _buildToolbar() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: _backgroundColor,
        border: Border(
          bottom: BorderSide(
            color: _isDarkMode
                ? Colors.white.withValues(alpha: 0.06)
                : Colors.grey[200]!,
          ),
        ),
      ),
      child: Row(
        children: [
          IconButton(
            icon: Icon(
              Icons.chevron_left,
              color: _textColor.withValues(
                alpha: _currentChapterIndex > 0 ? 1.0 : 0.3,
              ),
            ),
            onPressed: _currentChapterIndex > 0
                ? () {
                    setState(() {
                      _currentChapterIndex--;
                      _showTranslation = false;
                      _translatedContent = null;
                    });
                    _scrollController.jumpTo(0);
                  }
                : null,
            tooltip: 'Предыдущая глава',
            splashRadius: 18,
            constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
            padding: EdgeInsets.zero,
          ),
          Expanded(
            child: GestureDetector(
              onTap: () {
                final renderBox = context.findRenderObject() as RenderBox;
                showMenu<int>(
                  context: context,
                  position: RelativeRect.fromRect(
                    Rect.fromLTWH(
                      60,
                      kToolbarHeight + 4,
                      renderBox.size.width - 120,
                      0,
                    ),
                    Offset.zero & renderBox.size,
                  ),
                  color: _isDarkMode ? const Color(0xFF2A2A3E) : Colors.white,
                  elevation: 8,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                  items: List.generate(_totalChapters, (index) {
                    final chapters = widget.document.chapters.isNotEmpty
                        ? widget.document.chapters
                        : _autoChapters;
                    final chapterTitle =
                        chapters[index]['title']?.toString() ??
                        'Глава ${index + 1}';
                    final isCurrent = index == _currentChapterIndex;
                    return PopupMenuItem<int>(
                      value: index,
                      child: Row(
                        children: [
                          Container(
                            width: 24,
                            height: 24,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: isCurrent
                                  ? _buttonColor
                                  : Colors.grey[200],
                            ),
                            child: Center(
                              child: Text(
                                '${index + 1}',
                                style: GoogleFonts.inter(
                                  color: isCurrent
                                      ? Colors.white
                                      : Colors.grey[600],
                                  fontSize: 11,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              chapterTitle,
                              style: GoogleFonts.inter(
                                color: _textColor,
                                fontWeight: isCurrent
                                    ? FontWeight.w600
                                    : FontWeight.w400,
                                fontSize: 13,
                              ),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          if (isCurrent)
                            Icon(Icons.check, color: _buttonColor, size: 16),
                        ],
                      ),
                    );
                  }),
                ).then((index) {
                  if (index != null && index != _currentChapterIndex) {
                    setState(() {
                      _currentChapterIndex = index;
                      _showTranslation = false;
                      _translatedContent = null;
                    });
                    _scrollController.jumpTo(0);
                  }
                });
              },
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: _buttonColor.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: _buttonColor.withValues(alpha: 0.2),
                  ),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.layers, size: 13, color: _buttonColor),
                    const SizedBox(width: 4),
                    Flexible(
                      child: Text(
                        _currentTitle.length < 25
                            ? _currentTitle
                            : 'Глава ${_currentChapterIndex + 1}',
                        style: GoogleFonts.inter(
                          color: _buttonColor,
                          fontWeight: FontWeight.w600,
                          fontSize: 11,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    const SizedBox(width: 2),
                    Text(
                      '${_currentChapterIndex + 1}/$_totalChapters',
                      style: GoogleFonts.inter(
                        color: _buttonColor.withValues(alpha: 0.6),
                        fontWeight: FontWeight.w400,
                        fontSize: 10,
                      ),
                    ),
                    const SizedBox(width: 2),
                    Icon(
                      Icons.keyboard_arrow_down,
                      size: 14,
                      color: _buttonColor,
                    ),
                  ],
                ),
              ),
            ),
          ),
          IconButton(
            icon: Icon(
              Icons.chevron_right,
              color: _textColor.withValues(
                alpha: _currentChapterIndex < _totalChapters - 1 ? 1.0 : 0.3,
              ),
            ),
            onPressed: _currentChapterIndex < _totalChapters - 1
                ? () {
                    setState(() {
                      _currentChapterIndex++;
                      _showTranslation = false;
                      _translatedContent = null;
                    });
                    _scrollController.jumpTo(0);
                  }
                : null,
            tooltip: 'Следующая глава',
            splashRadius: 18,
            constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
            padding: EdgeInsets.zero,
          ),
          _buildFontSizeButton(-1, Icons.text_decrease, 'Уменьшить шрифт'),
          _buildFontSizeButton(1, Icons.text_increase, 'Увеличить шрифт'),
          Container(
            margin: const EdgeInsets.symmetric(horizontal: 2),
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: _buttonColor.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              '${_fontSize.toInt()}',
              style: GoogleFonts.inter(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: _buttonColor,
              ),
            ),
          ),
          _buildBookmarkButton(),
          if (widget.document.language != 'ru' &&
              widget.document.language.isNotEmpty)
            _buildTranslateButton(),
        ],
      ),
    );
  }

  Widget _buildTranslateButton() {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      child: ElevatedButton.icon(
        onPressed: _isTranslating ? null : _toggleTranslation,
        icon: Icon(
          _showTranslation ? Icons.text_fields : Icons.translate,
          size: 14,
        ),
        label: Text(
          _showTranslation
              ? 'Оригинал'
              : _isTranslating
              ? 'Перевод...'
              : 'Перевести',
          style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w500),
        ),
        style: ElevatedButton.styleFrom(
          backgroundColor: _showTranslation
              ? _buttonColor.withValues(alpha: 0.12)
              : _buttonColor,
          foregroundColor: _showTranslation ? _textColor : Colors.white,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          minimumSize: Size.zero,
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
          elevation: _showTranslation ? 0 : 2,
          shadowColor: _buttonColor.withValues(alpha: 0.3),
        ),
      ),
    );
  }

  Widget _buildNavigationPanel() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: _backgroundColor,
        border: Border(
          top: BorderSide(
            color: _isDarkMode
                ? Colors.white.withValues(alpha: 0.06)
                : Colors.grey[200]!,
          ),
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          SizedBox(
            height: 40,
            child: ElevatedButton.icon(
              onPressed: _currentChapterIndex > 0
                  ? () {
                      setState(() {
                        _currentChapterIndex--;
                        _showTranslation = false;
                        _translatedContent = null;
                      });
                      _scrollController.jumpTo(0);
                    }
                  : null,
              icon: Icon(
                Icons.chevron_left,
                size: 20,
                color: _currentChapterIndex > 0
                    ? _textColor
                    : _textColor.withValues(alpha: 0.3),
              ),
              label: Text(
                'Назад',
                style: GoogleFonts.inter(
                  color: _currentChapterIndex > 0
                      ? _textColor
                      : _textColor.withValues(alpha: 0.3),
                ),
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor: _isDarkMode
                    ? Colors.white.withValues(alpha: 0.08)
                    : Colors.grey[100],
                elevation: 0,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 12),
              ),
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            decoration: BoxDecoration(
              color: _isDarkMode
                  ? Colors.white.withValues(alpha: 0.06)
                  : Colors.grey[100],
              borderRadius: BorderRadius.circular(12),
            ),
            child: PopupMenuButton<int>(
              icon: Icon(Icons.list, color: _textColor, size: 20),
              color: _isDarkMode ? const Color(0xFF2A2A3E) : Colors.white,
              elevation: 8,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
              itemBuilder: (context) {
                final chapters = widget.document.chapters.isNotEmpty
                    ? widget.document.chapters
                    : _autoChapters;

                return List.generate(chapters.length, (index) {
                  final notesCount = _notes
                      .where((note) => note.chapterIndex == index)
                      .length;

                  return PopupMenuItem(
                    value: index,
                    child: Row(
                      children: [
                        Container(
                          width: 26,
                          height: 26,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: _currentChapterIndex == index
                                ? _buttonColor
                                : Colors.grey[200],
                          ),
                          child: Center(
                            child: Text(
                              '${index + 1}',
                              style: GoogleFonts.inter(
                                color: _currentChapterIndex == index
                                    ? Colors.white
                                    : Colors.grey[600],
                                fontSize: 12,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                chapters[index]['title']?.toString() ??
                                    'Глава ${index + 1}',
                                style: GoogleFonts.inter(
                                  color: _textColor,
                                  fontWeight: _currentChapterIndex == index
                                      ? FontWeight.w600
                                      : FontWeight.w400,
                                  fontSize: 14,
                                ),
                                overflow: TextOverflow.ellipsis,
                              ),
                              if (notesCount > 0)
                                Row(
                                  children: [
                                    Icon(
                                      Icons.note,
                                      size: 10,
                                      color: _buttonColor,
                                    ),
                                    const SizedBox(width: 2),
                                    Text(
                                      '$notesCount',
                                      style: GoogleFonts.inter(fontSize: 10),
                                    ),
                                  ],
                                ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  );
                });
              },
              onSelected: (index) {
                setState(() {
                  _currentChapterIndex = index;
                  _showTranslation = false;
                  _translatedContent = null;
                });
                _scrollController.jumpTo(0);
              },
            ),
          ),
          SizedBox(
            height: 40,
            child: ElevatedButton.icon(
              onPressed: _currentChapterIndex < _totalChapters - 1
                  ? () {
                      setState(() {
                        _currentChapterIndex++;
                        _showTranslation = false;
                        _translatedContent = null;
                      });
                      _scrollController.jumpTo(0);
                    }
                  : null,
              icon: Icon(
                Icons.chevron_right,
                size: 20,
                color: _currentChapterIndex < _totalChapters - 1
                    ? _textColor
                    : _textColor.withValues(alpha: 0.3),
              ),
              label: Text(
                'Вперед',
                style: GoogleFonts.inter(
                  color: _currentChapterIndex < _totalChapters - 1
                      ? _textColor
                      : _textColor.withValues(alpha: 0.3),
                ),
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor: _isDarkMode
                    ? Colors.white.withValues(alpha: 0.08)
                    : Colors.grey[100],
                elevation: 0,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 12),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
