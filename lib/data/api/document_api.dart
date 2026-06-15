import 'dart:convert';
import 'dart:io';
import 'package:dio/dio.dart';
import 'package:crypto/crypto.dart';
import 'package:versevo_app/data/api/api_client.dart';
import 'package:versevo_app/data/models/document_model.dart';

class DocumentApi {
  final Dio _dio = ApiClient.getInstance().dio;

  final Map<String, Map<String, dynamic>> _translationCache = {};
  final Map<int, DocumentModel> _localDocuments = {};
  List<DocumentModel>? _cachedDocumentList;
  DateTime? _lastFetchTime;
  static const Duration _cacheDuration = Duration(seconds: 30);

  Future<Map<String, dynamic>> translateText(
      String text,
      String targetLanguage, {
        String sourceLanguage = 'auto',
        String style = 'artistic',
      }) async {
    try {
      final hash = _generateHash(text);
      final cached = _translationCache[hash];
      if (cached != null) return cached;

      final textToTranslate = text.length > 5000
          ? text.substring(0, 5000) + '...'
          : text;

      final response = await _dio.post(
        '/api/translate/text',
        data: {
          'text': textToTranslate,
          'target_language': targetLanguage,
          'source_language': sourceLanguage,
          'style': style,
        },
        options: Options(
          validateStatus: (status) => status! < 500,
          sendTimeout: const Duration(seconds: 60),
          receiveTimeout: const Duration(seconds: 60),
        ),
      );

      if (response.statusCode == 200) {
        final Map<String, dynamic> data = response.data;

        String? translatedText;
        if (data.containsKey('translated_text')) {
          translatedText = data['translated_text'];
        } else if (data.containsKey('translatedText')) {
          translatedText = data['translatedText'];
        } else if (data.containsKey('text')) {
          translatedText = data['text'];
        }

        if (translatedText != null && translatedText.isNotEmpty) {
          final translation = {
            'translated_text': translatedText,
            'original_text': text,
            'source_language': data['source_language'] ?? sourceLanguage,
            'target_language': data['target_language'] ?? targetLanguage,
            'style': data['style'] ?? style,
            'translation_service': data['translation_service'] ?? 'backend'
          };

          _translationCache[hash] = translation;
          return translation;
        }
      }

      return _createFallbackTranslation(text, targetLanguage, sourceLanguage, style);
    } on DioException {
      return _createFallbackTranslation(text, targetLanguage, sourceLanguage, style);
    } catch (e) {
      return _createFallbackTranslation(text, targetLanguage, sourceLanguage, style);
    }
  }

  String _generateHash(String text) {
    final bytes = utf8.encode(text);
    final digest = sha256.convert(bytes);
    return digest.toString();
  }

  Map<String, dynamic> _createFallbackTranslation(
      String text,
      String targetLanguage,
      String sourceLanguage,
      String style,
      ) {
    return {
      'translated_text': text,
      'original_text': text,
      'source_language': sourceLanguage,
      'target_language': targetLanguage,
      'style': style,
      'translation_service': 'offline_fallback'
    };
  }

  Future<DocumentModel> getDocumentWithContent(int id) async {
    try {
      final response = await _dio.get(
        '/api/documents/$id',
        options: Options(
          validateStatus: (status) => status! < 500,
        ),
      );

      if (response.statusCode == 200) {
        if (response.data == null) {
          throw Exception('Сервер вернул пустой ответ');
        }

        final document = DocumentModel.fromJson(response.data);
        _localDocuments[id] = document;
        return document;
      } else if (response.statusCode == 404) {
        final doc = _localDocuments[id];
        if (doc != null) return doc;
        throw Exception('Документ не найден');
      } else {
        throw Exception('Ошибка сервера: ${response.statusCode}');
      }
    } on DioException catch (e) {
      final doc = _localDocuments[id];
      if (doc != null) return doc;

      if (e.type == DioExceptionType.connectionError ||
          e.type == DioExceptionType.connectionTimeout ||
          e.response?.statusCode == 502) {
        throw Exception('Сервер недоступен. Проверьте подключение.');
      }

      throw Exception('Не удалось загрузить документ: ${e.message}');
    } catch (e) {
      final doc = _localDocuments[id];
      if (doc != null) return doc;
      rethrow;
    }
  }

  Future<Map<String, dynamic>> translateDocument(int documentId, String targetLanguage) async {
    try {
      final response = await _dio.post(
        '/api/translate/document/$documentId',
        data: {'target_language': targetLanguage},
        options: Options(
          validateStatus: (status) => status! < 500,
          sendTimeout: const Duration(seconds: 30),
          receiveTimeout: const Duration(seconds: 30),
        ),
      );

      if (response.statusCode == 200) {
        final result = response.data;
        if (result.containsKey('translated_document_id')) {
          final translatedDocId = result['translated_document_id'];
          final translatedDoc = await getDocumentWithContent(translatedDocId);
          _localDocuments[translatedDocId] = translatedDoc;
        }
        return result;
      } else {
        throw Exception('Ошибка перевода: ${response.statusCode}');
      }
    } on DioException catch (e) {
      throw Exception('Не удалось перевести документ: ${e.message}');
    }
  }

  Future<List<DocumentModel>> getDocuments() async {
    if (_cachedDocumentList != null && _lastFetchTime != null) {
      if (DateTime.now().difference(_lastFetchTime!) < _cacheDuration) {
        return _cachedDocumentList!;
      }
    }

    try {
      final response = await _dio.get(
        '/api/documents',
        options: Options(
          validateStatus: (status) => status! < 500,
        ),
      );

      if (response.statusCode == 200 && response.data != null) {
        final List<dynamic> data = response.data is List ? response.data : [];
        final documents = <DocumentModel>[];
        for (var json in data) {
          try {
            final doc = DocumentModel.fromJson(json);
            documents.add(doc);
            _localDocuments[doc.id] = doc;
          } catch (_) {}
        }

        for (var localDoc in _localDocuments.values) {
          if (!documents.any((d) => d.id == localDoc.id)) {
            documents.add(localDoc);
          }
        }

        _cachedDocumentList = documents;
        _lastFetchTime = DateTime.now();
        return documents;
      } else {
        return _localDocuments.values.toList();
      }
    } on DioException {
      return _localDocuments.values.toList();
    } catch (e) {
      return _localDocuments.values.toList();
    }
  }

  Future<DocumentModel> uploadDocument(File file) async {
    try {
      final bytes = await file.readAsBytes();
      final base64String = base64Encode(bytes);
      final fileName = file.path.split('\\').last.split('/').last;

      if (bytes.length > 10 * 1024 * 1024) {
        throw Exception('Файл слишком большой (максимум 10MB)');
      }

      final response = await _dio.post(
        '/api/documents/upload-base64',
        data: {
          'filename': fileName,
          'file_data': base64String,
          'file_size': bytes.length,
        },
        options: Options(
          validateStatus: (status) => status! < 500,
          sendTimeout: const Duration(seconds: 60),
          receiveTimeout: const Duration(seconds: 60),
        ),
      );

      if (response.statusCode == 200) {
        if (response.data == null) {
          throw Exception('Сервер вернул пустой ответ');
        }

        if (response.data is Map<String, dynamic>) {
          final data = response.data as Map<String, dynamic>;

          if (data['id'] == null) {
            throw Exception('Сервер не вернул ID документа');
          }

          final document = DocumentModel.fromJson(data);
          _localDocuments[document.id] = document;
          _cachedDocumentList = null;
          return document;
        } else {
          throw Exception('Некорректный ответ сервера');
        }
      } else {
        String errorMessage = 'Ошибка загрузки';
        if (response.data != null) {
          if (response.data is Map) {
            errorMessage = response.data['detail'] ??
                response.data['message'] ??
                'Ошибка сервера: ${response.statusCode}';
          } else if (response.data is String) {
            errorMessage = response.data;
          }
        }
        throw Exception(errorMessage);
      }
    } on DioException catch (e) {
      if (e.response?.statusCode == 502) {
        throw Exception('Сервер временно недоступен (502).\nВозможно, сервер запускается — попробуйте через минуту.');
      }
      if (e.type == DioExceptionType.sendTimeout || e.type == DioExceptionType.receiveTimeout) {
        throw Exception('Таймаут загрузки. Сервер на Railway может быть в режиме сна.\nПопробуйте ещё раз через 30 секунд.');
      }
      if (e.type == DioExceptionType.connectionError) {
        throw Exception('Проверьте подключение к интернету.');
      }

      String serverMessage = 'Неизвестная ошибка';
      if (e.response?.data != null) {
        if (e.response!.data is Map) {
          serverMessage = e.response!.data['detail'] ??
              e.response!.data['message'] ??
              'Ошибка сервера: ${e.response!.statusCode}';
        } else {
          serverMessage = e.response!.data.toString();
        }
      }
      throw Exception('Ошибка загрузки: $serverMessage');
    } catch (e) {
      rethrow;
    }
  }

  Future<DocumentModel> getDocument(int id) async {
    return getDocumentWithContent(id);
  }

  Future<bool> deleteDocument(int id) async {
    try {
      final response = await _dio.delete(
        '/api/documents/$id',
        options: Options(validateStatus: (status) => status! < 500),
      );

      _localDocuments.remove(id);
      _cachedDocumentList = null;

      return response.statusCode == 200;
    } on DioException {
      _localDocuments.remove(id);
      _cachedDocumentList = null;
      return true;
    } catch (e) {
      _localDocuments.remove(id);
      _cachedDocumentList = null;
      return true;
    }
  }
}
