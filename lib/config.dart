import 'package:dio/dio.dart';

class AppConfig {
  // Railway URL
  static const String apiBaseUrl = 'https://versevo-backend-production.up.railway.app';

  // Статус сервера
  static String get serverStatusUrl => '$apiBaseUrl/api/flutter/health';

  // Основные эндпоинты
  static String get authUrl => '$apiBaseUrl/api/auth';
  static String get documentsUrl => '$apiBaseUrl/api/documents';
  static String get translateUrl => '$apiBaseUrl/api/translate/text';
  static String get analyzeUrl => '$apiBaseUrl/api/analyze';

  // Проверить доступность сервера
  static Future<bool> checkServerAvailability() async {
    try {
      final response = await Dio().get(serverStatusUrl,
          options: Options(receiveTimeout: const Duration(seconds: 10))
      );
      return response.statusCode == 200;
    } catch (e) {
      print('❌ Сервер недоступен: $e');
      return false;
    }
  }
}