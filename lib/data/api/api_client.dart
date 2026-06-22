import 'dart:async';
import 'package:dio/dio.dart';
import 'package:shared_preferences/shared_preferences.dart';

class ApiClient {
  static const String _baseUrl = 'https://versevo-backend-production.up.railway.app';
  static bool _warmupDone = false;

  late Dio _dio;

  ApiClient._internal() {
    _dio = Dio(BaseOptions(
      baseUrl: _baseUrl,
      connectTimeout: const Duration(seconds: 30),
      receiveTimeout: const Duration(seconds: 30),
      headers: {
        'Content-Type': 'application/json',
      },
    ));

    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        try {
          final prefs = await SharedPreferences.getInstance();
          final token = prefs.getString('auth_token');
          if (token != null && token.isNotEmpty) {
            options.headers['Authorization'] = 'Bearer $token';
          }
        } catch (_) {}
        return handler.next(options);
      },
      onError: (DioException e, handler) async {
        if (e.response?.statusCode == 401) {
          try {
            final prefs = await SharedPreferences.getInstance();
            await prefs.clear();
          } catch (_) {}
        }
        return handler.next(e);
      },
    ));

    _dio.interceptors.add(RetryInterceptor(dio: _dio));

    _warmupServer();
  }

  Future<void> _warmupServer() async {
    if (_warmupDone) return;
    _warmupDone = true;
    try {
      await _dio.get('/api/health', options: Options(
        sendTimeout: const Duration(seconds: 30),
        receiveTimeout: const Duration(seconds: 30),
      ));
    } catch (_) {}
  }

  Dio get dio => _dio;

  static final ApiClient _instance = ApiClient._internal();

  static ApiClient getInstance() => _instance;

  factory ApiClient() => _instance;
}

class RetryInterceptor extends Interceptor {
  final Dio dio;
  final int maxRetries;

  RetryInterceptor({required this.dio, this.maxRetries = 2});

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    final retryCount = err.requestOptions.extra['retryCount'] as int? ?? 0;

    if (_shouldRetry(err) && retryCount < maxRetries) {
      err.requestOptions.extra['retryCount'] = retryCount + 1;
      await Future.delayed(Duration(seconds: 2 * (retryCount + 1)));
      try {
        final response = await dio.fetch(err.requestOptions);
        return handler.resolve(response);
      } catch (retryErr) {
        return handler.next(err);
      }
    }
    return handler.next(err);
  }

  bool _shouldRetry(DioException err) {
    return err.type == DioExceptionType.connectionTimeout ||
        err.type == DioExceptionType.connectionError ||
        err.type == DioExceptionType.receiveTimeout ||
        err.response?.statusCode == 502 ||
        err.response?.statusCode == 503;
  }
}
