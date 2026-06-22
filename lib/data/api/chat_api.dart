import 'dart:async';
import 'package:dio/dio.dart';
import 'package:versevo_app/data/api/api_client.dart';

class ChatApi {
  final Dio _dio;
  final Dio _hfDio;
  static const String _hfApiKey = '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';

  /// Models that work reliably on HF free Inference API
  /// flan-t5-xl (3B) — best balance of capability & availability
  /// flan-t5-large (780M) — reliable fallback
  /// flan-t5-base (250M) — last resort
  static const _models = [
    'google/flan-t5-xl',
    'google/flan-t5-large',
    'google/flan-t5-base',
  ];

  String? _cachedContent;

  ChatApi()
      : _dio = ApiClient.getInstance().dio,
        _hfDio = Dio(BaseOptions(
          connectTimeout: const Duration(seconds: 120),
          receiveTimeout: const Duration(seconds: 180),
          headers: {
            'Authorization': 'Bearer $_hfApiKey',
            'Content-Type': 'application/json',
          },
        )) {
    _dio.options.connectTimeout = const Duration(seconds: 10);
    _dio.options.receiveTimeout = const Duration(seconds: 20);
  }

  Future<String> askQuestion({
    required int documentId,
    required String question,
    String? documentContent,
    List<Map<String, String>> conversationHistory = const [],
  }) async {
    // 1. Try backend first — best connectivity to HF API
    try {
      final response = await _dio
          .post(
            '/api/chat/ask',
            data: {
              'document_id': documentId,
              'question': question,
              'history': conversationHistory,
            },
            options: Options(
              sendTimeout: const Duration(seconds: 15),
              receiveTimeout: const Duration(seconds: 30),
            ),
          )
          .timeout(const Duration(seconds: 35), onTimeout: () {
        throw TimeoutException('backed timeout');
      });

      if (response.statusCode == 200 && response.data is Map) {
        final data = response.data as Map<String, dynamic>;
        final answer = data['answer']?.toString() ?? '';
        if (answer.isNotEmpty && !_isTemplateResponse(answer)) return answer;
      }
    } catch (_) {}

    // 2. Fallback: fetch content and call HF directly
    if (documentContent == null || documentContent.isEmpty) {
      if (_cachedContent != null) {
        documentContent = _cachedContent;
      } else {
        documentContent = await _fetchDocumentContent(documentId);
        _cachedContent = documentContent;
      }
    }

    final cleanContent = _stripImages(documentContent ?? '');
    final contextChunk = _extractRelevantContext(cleanContent, question);

    final hfAnswer = await _askHuggingFace(contextChunk, question, conversationHistory);
    if (hfAnswer != null && hfAnswer.isNotEmpty) return hfAnswer;

    // 3. If both fail — deep document analysis fallback
    return _deepFallback(cleanContent, question);
  }

  String _extractRelevantContext(String content, String question) {
    if (content.length <= 1500) return content;

    final paragraphs = content.split('\n\n').where((p) => p.trim().length > 20).toList();
    if (paragraphs.isEmpty) return content.substring(0, 1500);

    final keywords = question
        .toLowerCase()
        .replaceAll(RegExp(r'[^\w\sа-яё]'), '')
        .split(RegExp(r'\s+'))
        .where((w) => w.length > 2)
        .toList();

    if (keywords.isEmpty) return content.substring(0, 1500);

    final scored = <int>[];
    for (int i = 0; i < paragraphs.length; i++) {
      final lower = paragraphs[i].toLowerCase();
      int score = 0;
      for (final kw in keywords) {
        if (lower.contains(kw)) score += kw.length;
      }
      if (score > 0) scored.add(i);
    }

    if (scored.isEmpty) return content.substring(0, 1500);

    final included = <int>{};
    for (final idx in scored) {
      included.add(idx);
      if (idx > 0) included.add(idx - 1);
      if (idx < paragraphs.length - 1) included.add(idx + 1);
    }

    final selected = included.toList()..sort();
    final buffer = StringBuffer();
    int chars = 0;
    for (final idx in selected) {
      final add = paragraphs[idx];
      if (chars + add.length > 1500) break;
      buffer.writeln(add);
      buffer.writeln();
      chars += add.length;
    }

    final result = buffer.toString().trim();
    if (result.length < 200) return content.substring(0, 1500);
    return result;
  }

  Future<String?> _fetchDocumentContent(int documentId) async {
    try {
      final response = await _dio
          .get(
            '/api/documents/$documentId',
            options: Options(
              sendTimeout: const Duration(seconds: 60),
              receiveTimeout: const Duration(seconds: 90),
            ),
          )
          .timeout(const Duration(seconds: 120));

      if (response.statusCode == 200 && response.data is Map) {
        final data = response.data as Map<String, dynamic>;
        final content = data['content']?.toString() ?? '';
        if (content.isNotEmpty) return content;
      }
    } catch (e) {
      print('ChatApi._fetchDocumentContent error: $e');
    }
    return null;
  }

  Future<String?> _askHuggingFace(
    String contextChunk,
    String question,
    List<Map<String, String>> history,
  ) async {
    for (final model in _models) {
      try {
        final prompt = _buildPrompt(contextChunk, question, history);
        final response = await _callHF(model, prompt);
        if (response == null || response.isEmpty) continue;
        final cleaned = _cleanFlanResult(response, prompt);
        if (cleaned.length > 5) return cleaned;
      } catch (e) {
        print('HF chat error [$model]: $e');
      }
    }
    return null;
  }

  /// Simple prompt that flan-t5 models understand reliably
  String _buildPrompt(
    String contextChunk,
    String question,
    List<Map<String, String>> history,
  ) {
    final buf = StringBuffer();

    buf.writeln('Ответь на вопрос по тексту документа на русском языке.');
    buf.writeln('Анализируй текст: выдели главные темы, тезисы, факты, персонажей, статистику если есть.');
    buf.writeln('Если информации недостаточно, чётко скажи чего именно не хватает.');
    buf.writeln();

    if (contextChunk.isNotEmpty) {
      buf.writeln('Текст документа:');
      buf.writeln(contextChunk);
      buf.writeln();
    }

    buf.writeln('Вопрос: $question');
    buf.writeln('Ответ:');

    return buf.toString();
  }

  String _stripImages(String text) {
    if (text.isEmpty) return text;
    text = text.replaceAll(RegExp(r'<[iI][mM][gG]\b[^>]*>', multiLine: true), '');
    text = text.replaceAll(RegExp(r'<[iI][mM][aA][gG][eE]\b[^>]*>', multiLine: true), '');
    text = text.replaceAll(RegExp(r'!\[([^\]]*)\]\(([^)]*)\)'), '');
    text = text.replaceAll(RegExp(r'!\s*\[([^\]]*)\]\s*\(([^)]*)\)'), '');
    text = text.replaceAll(RegExp(r'data:image/[a-zA-Z]+(?:;base64)?,[^\s\)]+', caseSensitive: false), '');
    text = text.replaceAll(
        RegExp(r'\S+\.(png|jpg|jpeg|gif|svg|webp|bmp|ico|tiff?)(\?[^\s]*)?', caseSensitive: false), '');
    text = text.replaceAll(RegExp(r'\[image:[^\]]*\]', caseSensitive: false), '');
    text = text.replaceAll(RegExp(r'\(image:[^)]*\)', caseSensitive: false), '');
    text = text.replaceAll(RegExp(r'^\s*image\.(png|jpg|jpeg|gif)\s*$', caseSensitive: false, multiLine: true), '');
    return text.trim();
  }

  Future<String?> _callHF(String model, String prompt) async {
    for (int attempt = 0; attempt < 6; attempt++) {
      try {
        final response = await _hfDio.post(
          'https://api-inference.huggingface.co/models/$model',
          data: {
            'inputs': prompt,
            'parameters': {
              'max_new_tokens': 350,
              'temperature': 0.7,
              'do_sample': true,
            },
          },
          options: Options(
            sendTimeout: const Duration(seconds: 60),
            receiveTimeout: const Duration(seconds: 120),
          ),
        );

        if (response.statusCode == 503) {
          print('HF $model loading, retry $attempt...');
          await Future.delayed(Duration(seconds: 2 + attempt * 3));
          continue;
        }

        if (response.statusCode == 200 && response.data is List && response.data.isNotEmpty) {
          if (response.data[0] is Map) {
            final item = response.data[0] as Map;
            if (item.containsKey('error')) {
              print('HF $model error: ${item['error']}');
              break;
            }
            return item['generated_text']?.toString() ?? '';
          }
          if (response.data[0] is String) {
            return response.data[0] as String;
          }
        }

        print('HF $model unexpected: ${response.statusCode}');
      } on DioException catch (e) {
        if (e.response?.statusCode == 503) {
          print('HF $model loading (dio), retry $attempt...');
          await Future.delayed(Duration(seconds: 2 + attempt * 3));
          continue;
        }
        print('HF $model dio: $e');
      } catch (e) {
        print('HF $model error: $e');
      }
      break;
    }
    return null;
  }

  String _cleanFlanResult(String raw, String prompt) {
    var result = raw.trim();
    int idx = result.indexOf(prompt);
    if (idx >= 0) {
      result = result.substring(idx + prompt.length).trim();
    }

    const prefixes = ['Ответ:', 'ответ:', 'Assistant:', 'assistant:'];
    for (final p in prefixes) {
      if (result.startsWith(p)) {
        result = result.substring(p.length).trim();
        break;
      }
    }

    result = result.split('\n').where((l) => l.trim().isNotEmpty).join('\n').trim();
    if (result.length > 2000) result = result.substring(0, 2000);
    return result;
  }

  String _deepFallback(String content, String question) {
    final q = question.toLowerCase().trim();

    if (q.contains('привет') || q.contains('здравств') || q.contains('хай') || q == 'hello' || q == 'hi') {
      return 'Привет! Я AI-ассистент для анализа документов. Могу ответить на вопросы по тексту, помочь с пересказом или выделить главные мысли. Что тебя интересует?';
    }
    if (q.contains('кто ты') || q.contains('что ты') || q.contains('ты кто')) {
      return 'Я AI-ассистент для работы с документами. Могу анализировать текст, отвечать на вопросы по содержанию, выделять ключевые моменты и помогать с пониманием прочитанного. Задавай любые вопросы!';
    }
    if (q.contains('спасиб') || q.contains('благодар')) {
      return 'Пожалуйста! Если будут ещё вопросы — обращайся.';
    }
    if (q.contains('пока') || q.contains('до свидан')) {
      return 'До свидания! Если понадобится помощь — я здесь.';
    }

    if (content.isEmpty) {
      return 'Документ пуст или недоступен для чтения. Сначала загрузите документ.';
    }

    final sentences = content
        .split(RegExp(r'(?<=[.!?])\s+'))
        .map((s) => s.trim())
        .where((s) => s.length > 20)
        .toList();
    final words = content.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).toList();
    final wordCount = words.length;

    if (q.contains('о чём') || q.contains('о чем') || q.contains('суть') || q.contains('содержание') || q.contains('кратко') || q.contains('главн') || q.contains('тезис') || q.contains('иде')) {
      final keySentences = sentences.where((s) => s.length > 40 && s.length < 400).take(5).toList();
      if (keySentences.isNotEmpty) {
        return '📄 Документ ($wordCount слов, ${sentences.length} предложений)\n\n'
            'Ключевые фрагменты:\n\n'
            '${keySentences.asMap().entries.map((e) => '${e.key + 1}. ${e.value}').join('\n\n')}';
      }
      return '📄 Документ содержит $wordCount слов, ${sentences.length} предложений. Задайте более конкретный вопрос.';
    }

    if (q.contains('тема') || q.contains('персонаж') || q.contains('герой') || q.contains('упомин')) {
      final keywords = q
          .replaceAll(RegExp(r'какие|каких|кто|главные|основные'), '')
          .split(RegExp(r'\s+'))
          .where((w) => w.length > 3)
          .toList();
      final keySentences = sentences.where((s) {
        final lower = s.toLowerCase();
        return keywords.any((kw) => lower.contains(kw));
      }).take(4).toList();

      if (keySentences.isNotEmpty) {
        return 'По вашему запросу:\n\n${keySentences.asMap().entries.map((e) => '${e.key + 1}. ${e.value}').join('\n\n')}';
      }
      return 'В тексте документа не удалось найти информацию по вашему запросу. Попробуйте уточнить вопрос.';
    }

    if (q.contains('статист') || q.contains('слов') || q.contains('сколько') || q.contains('объем') || q.contains('объём')) {
      final avgLen = sentences.isNotEmpty ? wordCount / sentences.length : 0;
      return '📊 Статистика документа:\n\n'
          '• Слов: $wordCount\n'
          '• Предложений: ${sentences.length}\n'
          '• Средняя длина: ${avgLen.toStringAsFixed(1)} слов\n'
          '• Время чтения: ${(wordCount / 200).ceil()} мин';
    }

    if ((q.contains('найди') || q.contains('найти') || q.contains('поиск') || q.contains('абзац') || q.contains('где')) && q.length > 6) {
      final search = q
          .replaceAll(RegExp(r'(найди|найти|поиск|абзац|про|где|мне|пожалуйста)'), '')
          .trim();
      if (search.length > 2) {
        final idx = content.toLowerCase().indexOf(search);
        if (idx != -1) {
          final start = (idx - 150).clamp(0, content.length);
          final end = (idx + search.length + 250).clamp(0, content.length);
          return '🔍 По запросу «$search»:\n\n...${content.substring(start, end)}...';
        }
        return '🔍 По запросу «$search» ничего не найдено.';
      }
    }

    if (q.contains('перескаж') || q.contains('резюм') || q.contains(' summary') || q.contains('кратк')) {
      final firstSentences = sentences.take(5).toList();
      if (firstSentences.isNotEmpty) {
        return 'Краткое содержание:\n\n${firstSentences.map((s) => '• $s').join('\n')}';
      }
    }

    final questionWords = q.split(RegExp(r'\s+')).where((w) => w.length > 3).toList();
    final matching = sentences.where((s) {
      final lower = s.toLowerCase();
      return questionWords.any((w) => lower.contains(w));
    }).take(4).toList();

    if (matching.isNotEmpty) {
      return 'По вашему вопросу:\n\n${matching.asMap().entries.map((e) => '${e.key + 1}. ${e.value}').join('\n\n')}';
    }

    return 'По вашему вопросу не удалось найти информацию в тексте документа. '
        'Попробуйте:\n'
        '• «О чём этот документ?»\n'
        '• «Выдели основные тезисы»\n'
        '• «Найди абзац про ...»\n'
        '• «Какая статистика?»';
  }

  bool _isTemplateResponse(String text) {
    final lower = text.toLowerCase();
    return lower.contains('попробуйте задать вопрос конкретнее') ||
        lower.contains('не удалось найти информацию') ||
        lower.contains('не найдено');
  }
}
