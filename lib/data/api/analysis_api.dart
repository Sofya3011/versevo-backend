import 'dart:async';
import 'package:dio/dio.dart';
import 'package:flutter/widgets.dart';
import 'package:versevo_app/data/api/api_client.dart';

class AnalysisApi {
  final Dio _dio;
  final Dio _hfDio;
  static const String _hfApiKey = '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';

  final Map<String, Map<String, dynamic>> _analysisCache = {};
  final Map<String, List<String>> _quotesCache = {};
  bool _aiChecked = false;
  bool _aiAvailable = false;

  String _aiProvider = 'basic';

  AnalysisApi() : _dio = ApiClient.getInstance().dio, _hfDio = Dio(BaseOptions(
    connectTimeout: const Duration(seconds: 120),
    receiveTimeout: const Duration(seconds: 180),
    headers: {
      'Authorization': 'Bearer $_hfApiKey',
      'Content-Type': 'application/json',
    },
  )) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      autoDetectProvider();
    });
  }

  String _getAnalysisCacheKey(int documentId) => '${documentId}_$_aiProvider';
  String _getQuotesCacheKey(int documentId) => '${documentId}_$_aiProvider';

  String _stripImages(String text) {
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

  Future<Map<String, dynamic>> generateWithHF({
    required int documentId,
    required String documentContent,
  }) async {
    documentContent = _stripImages(documentContent);
    if (documentContent.length > 800) {
      documentContent = documentContent.substring(0, 800);
    }
    final String docTitle = 'документ $documentId';

    const models = [
      'google/flan-t5-base',
      'google/flan-t5-large',
      'google/flan-t5-small',
    ];

    for (final model in models) {
      try {
        final context = documentContent.isNotEmpty ? documentContent : docTitle;
        final prompt = 'Проанализируй текст на русском языке: $context\n\n'
            'Напиши: о чем этот текст, главная мысль, ключевые моменты, настроение и стиль.';

        final raw = await _callHF(model, prompt, maxTokens: 512);
        if (raw == null || raw.isEmpty) continue;

        final text = _cleanResult(raw, prompt);
        if (text.length < 20) continue;

        final lines = text.split('\n').where((l) => l.trim().length > 15).toList();
        if (lines.isEmpty) { lines.add(text); }

        String sentiment = 'Нейтральный';
        String writingStyle = 'Информационный';

        for (final line in lines) {
          final lower = line.toLowerCase();
          if (lower.contains('тон') || lower.contains('настроен')) {
            if (lower.contains('положитель')) { sentiment = 'Положительный'; }
            else if (lower.contains('отрицатель')) { sentiment = 'Отрицательный'; }
            else if (lower.contains('нейтральн')) { sentiment = 'Нейтральный'; }
          }
          if (lower.contains('стиль')) {
            if (lower.contains('художеств')) { writingStyle = 'Художественный'; }
            else if (lower.contains('научн')) { writingStyle = 'Научный'; }
            else if (lower.contains('публицист')) { writingStyle = 'Публицистический'; }
            else if (lower.contains('информац')) { writingStyle = 'Информационный'; }
          }
        }

        final overview = lines.isNotEmpty ? lines.first : text;
        final summary = lines.length > 2 ? lines.sublist(0, 2).join('\n') : text;
        final keyPoints = lines.length > 2 ? lines.sublist(0, 3) : ['Анализ завершен'];

        return {
          'document_id': documentId,
          'overview': overview,
          'summary': summary,
          'themes': '',
          'sentiment': sentiment,
          'writing_style': writingStyle,
          'key_points': keyPoints,
          'characters': [],
          'ai_analysis': true,
          'fallback': false,
          'analysis_timestamp': DateTime.now().toIso8601String(),
          'analysis_method': 'huggingface_direct',
          'ai_provider': 'huggingface_direct',
        };
      } catch (e) {
        print('HF analysis error [$model]: $e');
      }
    }

    return _getMockAnalysisData(documentId);
  }

  Future<String?> _callHF(String model, String prompt, {int maxTokens = 512}) async {
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
    result = result.split('\n').where((l) => l.trim().isNotEmpty).join('\n').trim();
    if (result.length > 800) result = result.substring(0, 800);
    return result;
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
      print('AnalysisApi._fetchDocumentContent error: $e');
    }
    return null;
  }

  Future<Map<String, dynamic>> analyzeWithAI(int documentId,
      {String type = "full", String? documentContent}) async {
    final cacheKey = _getAnalysisCacheKey(documentId);
    if (documentContent == null || documentContent.isEmpty) {
      documentContent = await _fetchDocumentContent(documentId);
    }
    try {
      if (_analysisCache.containsKey(cacheKey)) {
        final cached = _analysisCache[cacheKey];
        if (cached != null && cached['ai_analysis'] == true && cached['fallback'] != true) {
          return cached;
        }
      }

      if (!_aiAvailable) {
        final basic = await analyzeDocument(documentId, documentContent: documentContent);
        if (basic['fallback'] == true) {
          final hf = await generateWithHF(documentId: documentId, documentContent: documentContent ?? '');
          if (hf['ai_analysis'] == true) {
            _analysisCache[cacheKey] = hf;
            return hf;
          }
        }
        return basic;
      }

      String endpoint;
      Map<String, dynamic> data;

      if (_aiProvider == 'huggingface') {
        endpoint = '/api/analyze/ai/document';
        data = {'document_id': documentId, 'analysis_type': type, 'language': 'ru'};
      } else if (_aiProvider == 'gemini') {
        endpoint = '/api/analyze/gemini/document';
        data = {'document_id': documentId, 'analysis_type': type, 'language': 'ru'};
      } else {
        return await analyzeDocument(documentId, documentContent: documentContent);
      }

      final response = await _dio.post(
        endpoint,
        data: data,
        options: Options(
          sendTimeout: const Duration(seconds: 30),
          receiveTimeout: const Duration(seconds: 30),
        ),
      ).timeout(const Duration(seconds: 35));

      final result = response.data is Map<String, dynamic>
          ? response.data
          : Map<String, dynamic>.from(response.data ?? {});

      if (result['fallback'] == true || result['ai_analysis'] == false) {
        final basic = await analyzeDocument(documentId, documentContent: documentContent);
        if (basic['fallback'] == true) {
          final hf = await generateWithHF(documentId: documentId, documentContent: documentContent ?? '');
          if (hf['ai_analysis'] == true) {
            _analysisCache[cacheKey] = hf;
            return hf;
          }
        }
        return basic;
      }

      result['analysis_timestamp'] = DateTime.now().toIso8601String();
      result['analysis_method'] = _aiProvider;

      _analysisCache[cacheKey] = result;
      if (_analysisCache.length > 10) {
        _analysisCache.remove(_analysisCache.keys.first);
      }

      return result;

    } on TimeoutException {
      final hf = await generateWithHF(documentId: documentId, documentContent: documentContent ?? '');
      if (hf['ai_analysis'] == true) {
        _analysisCache[cacheKey] = hf;
        return hf;
      }
      return _getMockAnalysisData(documentId);
    } on DioException {
      return await analyzeDocument(documentId, documentContent: documentContent);
    } catch (e) {
      return await analyzeDocument(documentId, documentContent: documentContent);
    }
  }

  Future<List<String>> getAIQuotes(int documentId, {int limit = 5}) async {
    try {
      final cacheKey = _getQuotesCacheKey(documentId);

      if (_quotesCache.containsKey(cacheKey)) {
        return _quotesCache[cacheKey]!;
      }

      try {
        final response = await _dio.get(
          '/api/documents/$documentId/quotes',
          queryParameters: {'limit': limit},
          options: Options(
            sendTimeout: const Duration(seconds: 10),
            receiveTimeout: const Duration(seconds: 10),
          ),
        ).timeout(const Duration(seconds: 12));

        if (response.data is Map && response.data['quotes'] != null) {
          final quotes = List<String>.from(response.data['quotes']);
          _quotesCache[cacheKey] = quotes;
          if (_quotesCache.length > 10) {
            _quotesCache.remove(_quotesCache.keys.first);
          }
          return quotes;
        }
      } on DioException {
        return _getFallbackQuotes();
      }

      return _getFallbackQuotes();
    } on TimeoutException {
      return _getFallbackQuotes();
    } on DioException {
      return _getFallbackQuotes();
    } catch (e) {
      return _getFallbackQuotes();
    }
  }

  Future<Map<String, dynamic>> checkAIService() async {
    if (_aiChecked) {
      return {'available': _aiAvailable, 'provider': _aiProvider};
    }

    try {
      final response = await _dio.get(
        '/api/analyze/ai/health',
        options: Options(
          sendTimeout: const Duration(seconds: 8),
          receiveTimeout: const Duration(seconds: 8),
        ),
      ).timeout(const Duration(seconds: 10));

      if (response.data is Map) {
        final data = response.data as Map<String, dynamic>;
        _aiAvailable = data['status'] == 'healthy' || data['available'] == true;
      }
    } catch (_) {
      _aiAvailable = false;
    }

    _aiChecked = true;
    return {'available': _aiAvailable, 'provider': _aiProvider};
  }

  Future<Map<String, dynamic>> analyzeDocument(int documentId, {String? documentContent}) async {
    try {
      final cacheKey = _getAnalysisCacheKey(documentId);

      if (_analysisCache.containsKey(cacheKey)) {
        final cached = _analysisCache[cacheKey];
        if (cached != null) return cached;
      }

      final response = await _dio.post(
        '/api/analyze',
        data: {'document_id': documentId, 'analysis_type': 'full'},
        options: Options(
          sendTimeout: const Duration(seconds: 15),
          receiveTimeout: const Duration(seconds: 15),
        ),
      ).timeout(const Duration(seconds: 20));

      final result = response.data is Map<String, dynamic>
          ? response.data
          : Map<String, dynamic>.from(response.data ?? {});

      final isFallback = result['fallback'] == true || result['ai_analysis'] == false;

      if (isFallback && documentContent != null && documentContent.isNotEmpty) {
        final hf = await generateWithHF(documentId: documentId, documentContent: documentContent);
        if (hf['ai_analysis'] == true) {
          _analysisCache[cacheKey] = hf;
          return hf;
        }
      }

      final enhancedResult = {
        'summary': result['summary']?.toString() ?? 'Краткое содержание не доступно',
        'themes': result['themes']?.toString() ?? result['key_themes']?.join(', ') ?? 'Темы не определены',
        'sentiment': result['sentiment']?.toString() ?? 'Нейтральная',
        'writing_style': result['writing_style']?.toString() ?? 'Информационный',
        'key_points': result['key_points'] is List ? result['key_points'] : [
          'Документ содержит ${result['word_count'] ?? 'неизвестное количество'} слов',
          'Язык: ${result['language'] ?? 'не определен'}',
          'Сложность: ${result['complexity'] ?? 'не определена'}'
        ],
        'characters': result['characters'] is List ? result['characters'] : [],
        'document_id': documentId,
        'ai_analysis': result['ai_analysis'] ?? false,
        'fallback': result['fallback'] ?? true,
        'analysis_timestamp': DateTime.now().toIso8601String(),
        'analysis_method': 'basic',
        'ai_provider': 'basic',
      };

      _analysisCache[cacheKey] = enhancedResult;
      if (_analysisCache.length > 10) {
        _analysisCache.remove(_analysisCache.keys.first);
      }

      return enhancedResult;

    } on TimeoutException {
      final hf = await generateWithHF(documentId: documentId, documentContent: documentContent ?? '');
      if (hf['ai_analysis'] == true) {
        _analysisCache[_getAnalysisCacheKey(documentId)] = hf;
        return hf;
      }
      return _getMockAnalysisData(documentId);
    } on DioException {
      final hf = await generateWithHF(documentId: documentId, documentContent: documentContent ?? '');
      if (hf['ai_analysis'] == true) {
        _analysisCache[_getAnalysisCacheKey(documentId)] = hf;
        return hf;
      }
      return _getMockAnalysisData(documentId);
    } catch (e) {
      final hf = await generateWithHF(documentId: documentId, documentContent: documentContent ?? '');
      if (hf['ai_analysis'] == true) {
        _analysisCache[_getAnalysisCacheKey(documentId)] = hf;
        return hf;
      }
      return _getMockAnalysisData(documentId);
    }
  }

  Future<bool> addQuoteToFavorites({
    required int documentId,
    required String quote,
    required int startPosition,
    required int endPosition,
  }) async {
    try {
      try {
        final response = await _dio.post(
          '/api/quotes/favorites',
          data: {
            'document_id': documentId,
            'quote': quote,
            'start_position': startPosition,
            'end_position': endPosition,
            'timestamp': DateTime.now().toIso8601String(),
          },
          options: Options(
            sendTimeout: const Duration(seconds: 8),
            receiveTimeout: const Duration(seconds: 8),
          ),
        ).timeout(const Duration(seconds: 10));

        if (response.statusCode == 200 || response.statusCode == 201) {
          return true;
        }
      } catch (_) {}

      await Future.delayed(const Duration(milliseconds: 200));
      return true;

    } catch (e) {
      return false;
    }
  }

  Future<List<Map<String, dynamic>>> getFavoriteQuotes() async {
    try {
      try {
        final response = await _dio.get(
          '/api/quotes/favorites',
          options: Options(
            sendTimeout: const Duration(seconds: 8),
            receiveTimeout: const Duration(seconds: 8),
          ),
        ).timeout(const Duration(seconds: 10));

        if (response.data is List) {
          return List<Map<String, dynamic>>.from(response.data);
        }
      } catch (_) {}

      return _getMockFavoriteQuotes();
    } catch (e) {
      return _getMockFavoriteQuotes();
    }
  }

  void clearCache() {
    _analysisCache.clear();
    _quotesCache.clear();
  }

  void clearDocumentCache(int documentId) {
    final analysisKey = _getAnalysisCacheKey(documentId);
    final quotesKey = _getQuotesCacheKey(documentId);
    _analysisCache.remove(analysisKey);
    _quotesCache.remove(quotesKey);
  }

  Future<void> autoDetectProvider() async {
    final providers = ['huggingface', 'gemini', 'basic'];

    for (final provider in providers) {
      _aiProvider = provider;
      try {
        final health = await checkAIService();
        if (health['available'] == true) return;
      } catch (_) {}
    }

    _aiProvider = 'basic';
    _aiAvailable = false;
    _aiChecked = true;
  }

  String get aiProvider => _aiProvider;

  void setAIProvider(String provider) {
    final validProviders = ['huggingface', 'gemini', 'basic'];
    if (validProviders.contains(provider) && _aiProvider != provider) {
      _aiProvider = provider;
      clearCache();
    }
  }

  List<String> getAvailableProviders() {
    return ['huggingface', 'gemini', 'basic'];
  }

  String getProviderDisplayName(String provider) {
    final names = {
      'huggingface': 'Hugging Face',
      'gemini': 'Gemini AI',
      'basic': 'Базовый',
    };
    return names[provider] ?? provider;
  }

  Map<String, dynamic> _getMockAnalysisData(int documentId) {
    return {
      'document_id': documentId,
      'summary': 'Документ загружен. AI-генерация выполняется через облачный сервис — пожалуйста, подождите или откройте документ для чтения, затем вернитесь к анализу.',
      'characters': [
        {'name': 'Пример персонажа', 'role': 'Главный герой', 'importance': 'высокая'},
      ],
      'themes': 'Документ, Литература, Анализ',
      'sentiment': 'Нейтральная',
      'writing_style': 'Информационный',
      'key_points': [
        'Документ загружен и готов к анализу',
        'Облачный AI-сервис временно недоступен',
        'Попробуйте обновить или открыть документ в читалке',
        'После прочтения анализ будет точнее'
      ],
      'ai_analysis': false,
      'fallback': true,
      'analysis_timestamp': DateTime.now().toIso8601String(),
      'analysis_method': 'mock',
      'ai_provider': _aiProvider,
    };
  }

  List<String> _getFallbackQuotes() {
    return [
      'Чтение развивает мышление и воображение.',
      'Каждая книга — это новое приключение.',
      'Знания, полученные из книг, бесценны.',
      'Текст помогает нам понимать мир вокруг.',
      'Литература — это искусство слова.',
    ];
  }

  List<Map<String, dynamic>> _getMockFavoriteQuotes() {
    return [
      {
        'id': 1,
        'quote': 'Технологии должны служить людям, а не наоборот.',
        'document_title': 'Будущее образования',
        'document_id': 1,
        'created_at': DateTime.now().subtract(const Duration(days: 2)).toIso8601String(),
      },
      {
        'id': 2,
        'quote': 'Образование будущего - это симбиоз традиций и инноваций.',
        'document_title': 'Цифровая революция',
        'document_id': 2,
        'created_at': DateTime.now().subtract(const Duration(days: 5)).toIso8601String(),
      },
    ];
  }

  Map<String, dynamic> getCacheStats() {
    return {
      'analysis_cache_size': _analysisCache.length,
      'quotes_cache_size': _quotesCache.length,
      'ai_provider': _aiProvider,
    };
  }
}
