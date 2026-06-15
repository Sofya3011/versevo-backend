import 'dart:async';
import 'package:dio/dio.dart';
import 'package:versevo_app/data/api/api_client.dart';

class ChatApi {
  final Dio _dio;
  final Dio _hfDio;
  static const String _hfApiKey = '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';

  ChatApi() : _dio = ApiClient.getInstance().dio, _hfDio = Dio(BaseOptions(
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
  }) async {
    String? answer;

    try {
      final response = await _dio.post(
        '/api/chat/ask',
        data: {
          'document_id': documentId,
          'question': question,
        },
        options: Options(
          sendTimeout: const Duration(seconds: 15),
          receiveTimeout: const Duration(seconds: 30),
        ),
      ).timeout(const Duration(seconds: 35), onTimeout: () {
        throw TimeoutException('Сервер не отвечает. Попробуйте позже.');
      });

      if (response.statusCode == 200 && response.data is Map) {
        final data = response.data as Map<String, dynamic>;
        answer = data['answer']?.toString() ?? '';
        if (answer.isNotEmpty && !_isTemplateResponse(answer)) return answer;
      }
    } catch (_) {}

    if (documentContent == null || documentContent.isEmpty) {
      documentContent = await _fetchDocumentContent(documentId);
    }

    answer = await _askWithFallback(documentContent, question);
    if (answer != null && answer.isNotEmpty) return answer;

    return _smartFallback(question);
  }

  Future<String?> _fetchDocumentContent(int documentId) async {
    try {
      final response = await _dio.get(
        '/api/documents/$documentId',
        options: Options(
          sendTimeout: const Duration(seconds: 60),
          receiveTimeout: const Duration(seconds: 90),
        ),
      ).timeout(const Duration(seconds: 120));

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

  Future<String?> _askWithFallback(String? content, String question) async {
    String? hfAnswer;

    if (content != null && content.isNotEmpty) {
      hfAnswer = await _askHuggingFace(content, question);
      if (hfAnswer != null && hfAnswer.isNotEmpty) return hfAnswer;
    }

    hfAnswer = await _askHuggingFace('', question);
    if (hfAnswer != null && hfAnswer.isNotEmpty) return hfAnswer;

    return null;
  }

  String _stripImages(String text) {
    if (text.isEmpty) return text;
    text = text.replaceAll(RegExp(r'<[iI][mM][gG]\b[^>]*>', multiLine: true), '');
    text = text.replaceAll(RegExp(r'<[iI][mM][aA][gG][eE]\b[^>]*>', multiLine: true), '');
    text = text.replaceAll(RegExp(r'!\[([^\]]*)\]\(([^)]*)\)'), '');
    text = text.replaceAll(RegExp(r'!\s*\[([^\]]*)\]\s*\(([^)]*)\)'), '');
    text = text.replaceAll(RegExp(r'data:image/[a-zA-Z]+(?:;base64)?,[^\s\)]+', caseSensitive: false), '');
    text = text.replaceAll(RegExp(r'\S+\.(png|jpg|jpeg|gif|svg|webp|bmp|ico|tiff?)(\?[^\s]*)?', caseSensitive: false), '');
    text = text.replaceAll(RegExp(r'\[image:[^\]]*\]', caseSensitive: false), '');
    text = text.replaceAll(RegExp(r'\(image:[^)]*\)', caseSensitive: false), '');
    text = text.replaceAll(RegExp(r'^\s*image\.(png|jpg|jpeg|gif)\s*$', caseSensitive: false, multiLine: true), '');
    return text.trim();
  }

  Future<String?> _askHuggingFace(String content, String question) async {
    content = _stripImages(content);

    if (content.length > 800) content = content.substring(0, 800);

    const models = [
      'google/flan-t5-base',
      'google/flan-t5-small',
      'google/flan-t5-large',
    ];

    for (final model in models) {
      try {
        final prompt = content.isNotEmpty
            ? 'Ты полезный ассистент. Ответь на русском языке естественно.\n\n'
                'Контекст: $content\n\n'
                'Вопрос: $question\n\n'
                'Ответ:'
            : 'Ты полезный ассистент. Ответь на русском языке естественно.\n\n'
                'Вопрос: $question\n\n'
                'Ответ:';

        final response = await _callHF(model, prompt, maxTokens: 300);
        if (response == null || response.isEmpty) continue;

        final cleaned = _cleanResult(response, prompt);
        if (cleaned.length > 3) return cleaned;
      } catch (e) {
        print('HF chat error [$model]: $e');
      }
    }

    return null;
  }

  Future<String?> _callHF(String model, String prompt, {int maxTokens = 300}) async {
    for (int attempt = 0; attempt < 8; attempt++) {
      try {
        final response = await _hfDio.post(
          'https://api-inference.huggingface.co/models/$model',
          data: {
            'inputs': prompt,
            'parameters': {
              'max_new_tokens': maxTokens,
              'temperature': 0.7,
              'do_sample': true,
            },
          },
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

  String _cleanResult(String raw, String prompt) {
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
    if (result.length > 500) result = result.substring(0, 500);
    return result;
  }

  bool _isTemplateResponse(String text) {
    final lower = text.toLowerCase();
    return lower.contains('чтобы получить точный ответ') ||
        lower.contains('попробуйте:') ||
        lower.contains('найди абзац про') ||
        lower.contains('выдели основные тезисы') ||
        (lower.contains('документ') && lower.contains('слов') && lower.contains('попробуйте'));
  }

  String _smartFallback(String question) {
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
    if (q.contains('как дела') || q.contains('норм')) {
      return 'У меня всё отлично! Готов помочь с анализом документов. Что будем смотреть?';
    }
    if (q.contains('пока') || q.contains('до свидан')) {
      return 'До свидания! Если понадобится помощь — я здесь.';
    }
    if (q.contains('что ты умеешь') || q.contains('как ты работаешь')) {
      return 'Я умею:\n• Отвечать на вопросы по тексту документа\n• Выделять главные темы и идеи\n• Пересказывать содержание\n• Анализировать тон и стиль\n• Находить ключевые моменты\n\nПросто задай вопрос по документу!';
    }

    return 'Я не нашёл информации в тексте документа по вашему вопросу. Попробуйте переформулировать или спросить о конкретном содержании документа.';
  }
}
