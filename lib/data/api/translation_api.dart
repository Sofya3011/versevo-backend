import 'dart:convert';
import 'package:dio/dio.dart';
import 'api_client.dart';

class TranslationApi {
  final Dio _dio = Dio();
  static const String _hfApiKey = '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';
  static const String _model = 'facebook/nllb-200-distilled-600M';

  // Оптимизация: кэш переводов
  static final Map<String, String> _translationCache = {};

  Future<String> translateText({
    required String text,
    String sourceLanguage = 'en',
    String targetLanguage = 'ru',
    bool useCache = true,
  }) async {
    final cacheKey = '$sourceLanguage-$targetLanguage-${text.hashCode}';
    if (useCache && _translationCache.containsKey(cacheKey)) {
      print('✅ Используем кэшированный перевод');
      return _translationCache[cacheKey]!;
    }

    try {
      print('🔄 Пробуем backend API для перевода (${text.length} символов)');

      // Пробуем backend API
      try {
        final apiClient = ApiClient.getInstance();
        final response = await apiClient.dio.post(
          '/api/translate/text',
          data: {
            'text': text,
            'target_language': targetLanguage,
            'source_language': sourceLanguage,
          },
        );

        if (response.statusCode == 200) {
          final translated = response.data['translated_text'] as String;
          _translationCache[cacheKey] = translated;
          print('✅ Перевод через backend API успешен');
          return translated;
        }
      } catch (backendError) {
        print('⚠️ Backend API недоступен: $backendError');
      }

      // Fallback к HuggingFace
      print('🔄 Используем HuggingFace как fallback');
      return await _translateWithHuggingFace(text, sourceLanguage, targetLanguage);

    } catch (e) {
      print('❌ Все методы перевода не сработали: $e');
      // Последний fallback - возвращаем оригинал с пометкой
      return '[Перевод недоступен] $text';
    }
  }

  // Добавляем недостающий метод
  Future<String> _translateWithHuggingFace(
      String text,
      String sourceLanguage,
      String targetLanguage,
      ) async {
    try {
      print('🚀 Перевод через HuggingFace: ${text.length} символов');

      // Оптимизация: не переводим слишком длинные тексты целиком
      if (text.length > 4000) {
        print('⚠️ Текст слишком длинный, переводим первую часть');
        final firstPart = text.substring(0, 4000);
        final translatedPart = await _translateChunk(firstPart, sourceLanguage, targetLanguage);
        return '$translatedPart...';
      }

      return await _translateChunk(text, sourceLanguage, targetLanguage);
    } catch (e) {
      print('❌ Ошибка перевода HuggingFace: $e');
      rethrow;
    }
  }

  Future<String> _translateChunk(
      String text,
      String sourceLanguage,
      String targetLanguage,
      ) async {
    try {
      final apiUrl = 'https://api-inference.huggingface.co/models/$_model';

      final payload = {
        'inputs': text,
        'parameters': {
          'src_lang': _getNLLBCode(sourceLanguage),
          'tgt_lang': _getNLLBCode(targetLanguage),
          'max_length': 1024,
        },
      };

      final headers = {
        'Authorization': 'Bearer $_hfApiKey',
        'Content-Type': 'application/json',
      };

      final response = await _dio.post(
        apiUrl,
        data: jsonEncode(payload),
        options: Options(
          headers: headers,
          sendTimeout: const Duration(seconds: 45),
          receiveTimeout: const Duration(seconds: 45),
        ),
      );

      if (response.statusCode == 200) {
        final result = response.data;
        if (result is List && result.isNotEmpty) {
          final translation = result[0];
          if (translation is Map && translation.containsKey('translation_text')) {
            return translation['translation_text'] as String;
          }
        }
      } else if (response.statusCode == 503) {
        // Model is loading
        print('⏳ Модель загружается, ждем...');
        await Future.delayed(const Duration(seconds: 5));
        return await _translateChunk(text, sourceLanguage, targetLanguage);
      }

      throw Exception('API вернул неожиданный ответ: ${response.statusCode}');

    } catch (e) {
      print('❌ Ошибка в _translateChunk: $e');
      rethrow;
    }
  }

  String _getNLLBCode(String languageCode) {
    const codes = {
      'ru': 'rus_Cyrl', 'en': 'eng_Latn', 'de': 'deu_Latn',
      'fr': 'fra_Latn', 'es': 'spa_Latn', 'it': 'ita_Latn',
      'zh': 'zho_Hans', 'ar': 'arb_Arab', 'uk': 'ukr_Cyrl',
      'pl': 'pol_Latn', 'ja': 'jpn_Jpan', 'ko': 'kor_Hang',
    };
    return codes[languageCode] ?? 'eng_Latn';
  }

  // Быстрый перевод для предпросмотра
  Future<String> translatePreview(String text) async {
    if (text.length > 500) {
      text = text.substring(0, 500) + '...';
    }
    return translateText(text: text, useCache: true);
  }

  // Очистка кэша
  void clearCache() {
    _translationCache.clear();
  }
}