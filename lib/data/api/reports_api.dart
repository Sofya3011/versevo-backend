import 'package:dio/dio.dart';
import 'package:versevo_app/data/api/api_client.dart';

class ReportsApi {
  final Dio _dio = ApiClient.getInstance().dio;

  Future<Map<String, dynamic>> getSystemHealthReport() async {
    try {
      print('Запрос отчета здоровья системы');
      final response = await _dio.get('/api/reports/mock/system-health');
      return response.data;
    } catch (e) {
      print('Ошибка отчета здоровья: $e');
      return _getMockSystemHealth();
    }
  }

  Future<Map<String, dynamic>> getUserActivityReport({
    String? startDate,
    String? endDate,
  }) async {
    try {
      print('Запрос отчета активности пользователей');
      final params = <String, dynamic>{};
      if (startDate != null) params['start_date'] = startDate;
      if (endDate != null) params['end_date'] = endDate;

      final response = await _dio.get(
        '/api/reports/mock/user-activity',
        queryParameters: params,
      );

      return response.data;
    } catch (e) {
      print('Ошибка отчета активности: $e');
      return _getMockUserActivity();
    }
  }

  Future<Map<String, dynamic>> getDocumentStatisticsReport({
    String? language,
    String? fileType,
    int minWords = 0,
    int maxWords = 1000000,
  }) async {
    try {
      print('Запрос статистики документов');
      final response = await _dio.get(
        '/api/reports/mock/document-statistics',
        queryParameters: {
          if (language != null) 'language': language,
          if (fileType != null) 'file_type': fileType,
          'min_words': minWords,
          'max_words': maxWords,
        },
      );

      return response.data;
    } catch (e) {
      print('Ошибка отчета документов: $e');
      return _getMockDocumentStats();
    }
  }

  Future<Map<String, dynamic>> getTranslationUsageReport({
    String? startDate,
    String? endDate,
  }) async {
    try {
      print('Запрос отчета переводов');
      final params = <String, dynamic>{};
      if (startDate != null) params['start_date'] = startDate;
      if (endDate != null) params['end_date'] = endDate;

      final response = await _dio.get(
        '/api/reports/mock/translation-usage',
        queryParameters: params,
      );

      return response.data;
    } catch (e) {
      print('Ошибка отчета переводов: $e');
      return _getMockTranslations();
    }
  }

  Future<Map<String, dynamic>> getAiAnalysisReport({
    String? aiProvider,
    String? analysisType,
  }) async {
    try {
      print('Запрос отчета AI анализа');
      final response = await _dio.get(
        '/api/reports/mock/ai-analysis',
        queryParameters: {
          if (aiProvider != null) 'ai_provider': aiProvider,
          if (analysisType != null) 'analysis_type': analysisType,
        },
      );

      return response.data;
    } catch (e) {
      print('Ошибка отчета AI: $e');
      return _getMockAiAnalysis();
    }
  }

  Map<String, dynamic> _getMockSystemHealth() {
    return {
      "report_type": "system_health_mock",
      "timestamp": DateTime.now().toIso8601String(),
      "summary": {
        "total_users": 125,
        "active_users_7d": 58,
        "active_users_30d": 92,
        "retention_rate": 73.6
      },
      "table_statistics": {
        "users": 125,
        "documents": 89,
        "document_notes": 234,
        "document_analysis": 67,
        "favorite_quotes": 45,
      },
      "is_mock": true,
      "mock_warning": "Данные сгенерированы локально (сервер недоступен)"
    };
  }

  Map<String, dynamic> _getMockUserActivity() {
    return {
      "report_type": "user_activity_mock",
      "summary": {
        "total_users": 3,
        "active_users": 2,
        "total_documents": 25,
        "total_words_read": 258000,
        "activity_rate": 66.7
      },
      "data": [
        {
          "id": 1,
          "email": "admin@versevo.ru",
          "username": "admin",
          "documents_count": 12,
          "activity_status": "active"
        },
        {
          "id": 2,
          "email": "user@example.com",
          "username": "user1",
          "documents_count": 8,
          "activity_status": "active"
        },
        {
          "id": 3,
          "email": "inactive@test.com",
          "username": "old_user",
          "documents_count": 5,
          "activity_status": "inactive"
        }
      ],
      "is_mock": true,
      "mock_warning": "Данные для демонстрации"
    };
  }

  Map<String, dynamic> _getMockDocumentStats() {
    return {
      "report_type": "document_statistics_mock",
      "summary": {
        "total_documents": 3,
        "total_words": 686500,
        "avg_words": 228833.3,
        "languages_count": 2
      },
      "data": [
        {
          "filename": "Pride_and_Prejudice.pdf",
          "language": "en",
          "word_count": 125000,
          "reading_time_minutes": 625
        },
        {
          "filename": "Voyna_i_mir.txt",
          "language": "ru",
          "word_count": 560000,
          "reading_time_minutes": 2800
        },
        {
          "filename": "Les_Miserables.pdf",
          "language": "fr",
          "word_count": 530000,
          "reading_time_minutes": 2650
        }
      ],
      "is_mock": true,
      "mock_warning": "Данные для демонстрации"
    };
  }

  Map<String, dynamic> _getMockTranslations() {
    return {
      "report_type": "translation_usage_mock",
      "summary": {
        "total_translations": 23,
        "total_characters": 11700,
        "unique_translations": 19
      },
      "daily_data": [
        {
          "date": "2024-01-20",
          "translation_count": 15,
          "translation_service": "gemini"
        },
        {
          "date": "2024-01-21",
          "translation_count": 8,
          "translation_service": "gemini"
        },
        {
          "date": "2024-01-22",
          "translation_count": 0,
          "translation_service": "none"
        },
        {
          "date": "2024-01-23",
          "translation_count": 12,
          "translation_service": "openai"
        }
      ],
      "is_mock": true,
      "mock_warning": "Данные для демонстрации"
    };
  }

  Map<String, dynamic> _getMockAiAnalysis() {
    return {
      "report_type": "ai_analysis_mock",
      "summary": {
        "total_analysis": 8,
        "unique_documents": 5
      },
      "sentiment_distribution": [
        {"sentiment": "Положительный", "percentage": 60.0},
        {"sentiment": "Нейтральный", "percentage": 25.0},
        {"sentiment": "Отрицательный", "percentage": 15.0}
      ],
      "is_mock": true,
      "mock_warning": "Данные для демонстрации"
    };
  }
}
