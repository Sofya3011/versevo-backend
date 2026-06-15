import 'package:dio/dio.dart';
import 'package:versevo_app/data/api/api_client.dart';
import 'package:versevo_app/data/models/user_model.dart';

class AuthApi {
  final Dio _dio = ApiClient.getInstance().dio;

  // Моковые данные для пользователей
  final List<UserModel> _mockUsers = [];

  // Создаем пустого пользователя для обработки ошибок
  UserModel _createEmptyUser() {
    return UserModel(
      id: 0,
      email: '',
      username: '',
      token: '',
    );
  }

  Future<UserModel> login(String email, String password) async {
    try {
      print('🔐 Отправка запроса на вход: $email');

      final response = await _dio.post(
        '/api/auth/login',
        data: {
          'email': email,
          'password': password,
        },
        options: Options(
          validateStatus: (status) => status! < 500,
        ),
      );

      print('📥 Ответ сервера: ${response.statusCode}');

      if (response.statusCode == 200) {
        final user = UserModel.fromJson(response.data);
        print('✅ Вход успешен');

        // Сохраняем пользователя в моковые данные
        _mockUsers.removeWhere((u) => u.email == email);
        _mockUsers.add(user);

        return user;
      } else if (response.statusCode == 401) {
        throw response.data['detail'] ?? 'Неверный email или пароль';
      } else {
        throw response.data['detail'] ?? 'Ошибка сервера: ${response.statusCode}';
      }
    } on DioException catch (e) {
      print('❌ Ошибка входа: ${e.message}');
      print('Тип ошибки: ${e.type}');

      // Проверяем моковые данные
      final localUser = _mockUsers.firstWhere(
            (u) => u.email == email,
        orElse: () => _createEmptyUser(),
      );

      if (localUser.email.isNotEmpty) {
        print('✅ Используем пользователя из моковых данных');
        return localUser;
      }

      if (e.response != null) {
        print('Статус ответа: ${e.response!.statusCode}');
        print('Данные ответа: ${e.response!.data}');

        if (e.response!.data is Map) {
          throw e.response!.data['detail'] ?? 'Ошибка сервера';
        } else if (e.response!.data is String) {
          throw e.response!.data;
        }
      }

      if (e.type == DioExceptionType.connectionError ||
          e.type == DioExceptionType.connectionTimeout ||
          e.response?.statusCode == 502) {
        throw 'Сервер недоступен. Проверьте подключение к интернету.';
      }

      throw 'Ошибка сети: ${e.message}';
    } catch (e) {
      print('❌ Неизвестная ошибка: $e');
      throw 'Ошибка входа';
    }
  }

  Future<UserModel> register(String email, String password, String username) async {
    try {
      print('📝 Отправка запроса на регистрацию: $email ($username)');

      final response = await _dio.post(
        '/api/auth/register',
        data: {
          'email': email,
          'password': password,
          'username': username,
        },
        options: Options(
          validateStatus: (status) => status! < 500,
        ),
      );

      print('📥 Ответ сервера: ${response.statusCode}');

      if (response.statusCode == 200) {
        final user = UserModel.fromJson(response.data);
        print('✅ Регистрация успешна');

        // Сохраняем пользователя в моковые данные
        _mockUsers.removeWhere((u) => u.email == email);
        _mockUsers.add(user);

        return user;
      } else if (response.statusCode == 400) {
        throw response.data['detail'] ?? 'Ошибка регистрации';
      } else {
        throw response.data['detail'] ?? 'Ошибка сервера: ${response.statusCode}';
      }
    } on DioException catch (e) {
      print('❌ Ошибка регистрации: ${e.message}');
      print('Тип ошибки: ${e.type}');

      if (e.response != null) {
        print('Статус ответа: ${e.response!.statusCode}');
        print('Данные ответа: ${e.response!.data}');

        if (e.response!.data is Map) {
          throw e.response!.data['detail'] ?? 'Ошибка сервера';
        } else if (e.response!.data is String) {
          throw e.response!.data;
        }
      }

      if (e.type == DioExceptionType.connectionError ||
          e.type == DioExceptionType.connectionTimeout ||
          e.response?.statusCode == 502) {
        throw 'Сервер недоступен. Проверьте подключение к интернету.';
      }

      throw 'Ошибка сети: ${e.message}';
    } catch (e) {
      print('❌ Неизвестная ошибка: $e');
      throw 'Ошибка регистрации';
    }
  }

  Future<void> logout() async {
    try {
      print('👋 Выход из системы');
      await Future.delayed(const Duration(milliseconds: 300));
    } catch (e) {
      print('⚠️ Ошибка выхода: $e');
    }
  }

  Future<UserModel> getCurrentUser(String token) async {
    try {
      print('👤 Получение данных текущего пользователя');

      final response = await _dio.get(
        '/api/auth/me',
        options: Options(
          headers: {'Authorization': 'Bearer $token'},
          validateStatus: (status) => status! < 500,
        ),
      );

      if (response.statusCode == 200) {
        final user = UserModel.fromJson(response.data);
        return user;
      } else if (response.statusCode == 401) {
        throw 'Токен недействителен';
      } else {
        throw 'Ошибка сервера: ${response.statusCode}';
      }
    } on DioException catch (e) {
      print('❌ Ошибка получения данных пользователя: ${e.message}');
      throw 'Ошибка получения данных пользователя';
    }
  }
}