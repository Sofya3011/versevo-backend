import 'package:bloc/bloc.dart';
import 'package:equatable/equatable.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:versevo_app/data/api/auth_api.dart';
import 'package:versevo_app/data/models/user_model.dart';

part 'auth_event.dart';
part 'auth_state.dart';

class AuthBloc extends Bloc<AuthEvent, AuthState> {
  final AuthApi _authApi = AuthApi();
  final SharedPreferences _prefs;

  AuthBloc(SharedPreferences prefs)
      : _prefs = prefs,
        super(AuthInitial()) {
    on<AuthLoginEvent>(_onLogin);
    on<AuthRegisterEvent>(_onRegister);
    on<AuthLogoutEvent>(_onLogout);
    on<AuthCheckStatusEvent>(_onCheckStatus);
  }

  Future<void> _onLogin(
      AuthLoginEvent event,
      Emitter<AuthState> emit,
      ) async {
    emit(AuthLoading());
    try {
      print('🔐 Пытаемся войти с email: ${event.email}');

      final user = await _authApi.login(event.email, event.password);

      // Сохраняем данные
      await _prefs.setString('auth_token', user.token ?? '');
      await _prefs.setString('user_email', user.email);
      await _prefs.setString('user_username', user.username);
      await _prefs.setInt('user_id', user.id);

      print('✅ Вход успешен. Сохраняем данные');
      emit(AuthSuccess(user: user));
    } catch (e) {
      print('❌ Ошибка входа: $e');
      emit(AuthFailure(error: e.toString()));
    }
  }

  Future<void> _onRegister(
      AuthRegisterEvent event,
      Emitter<AuthState> emit,
      ) async {
    emit(AuthLoading());
    try {
      print('📝 Регистрация пользователя: ${event.username} (${event.email})');

      final user = await _authApi.register(
        event.email,
        event.password,
        event.username,
      );

      await _prefs.setString('auth_token', user.token ?? '');
      await _prefs.setString('user_email', user.email);
      await _prefs.setString('user_username', user.username);
      await _prefs.setInt('user_id', user.id);

      print('✅ Регистрация успешна');
      emit(AuthSuccess(user: user));
    } catch (e) {
      print('❌ Ошибка регистрации: $e');
      emit(AuthFailure(error: e.toString()));
    }
  }

  Future<void> _onLogout(
      AuthLogoutEvent event,
      Emitter<AuthState> emit,
      ) async {
    print('👋 Начинаем выход из системы');
    emit(AuthLoading());

    try {
      await _authApi.logout();

      // Очищаем ВСЕ данные
      await _prefs.remove('auth_token');
      await _prefs.remove('user_email');
      await _prefs.remove('user_username');
      await _prefs.remove('user_id');

      print('✅ Все данные удалены');
      print('   auth_token: ${_prefs.getString('auth_token')}');
      print('   user_email: ${_prefs.getString('user_email')}');

      emit(AuthInitial());
    } catch (e) {
      print('❌ Ошибка выхода: $e');
      emit(AuthFailure(error: e.toString()));
    }
  }
  Future<void> _onCheckStatus(
      AuthCheckStatusEvent event,
      Emitter<AuthState> emit,
      ) async {
    print('🔍 AuthBloc: Проверка статуса...');

    // НЕ ставим AuthLoading здесь - только в main.dart
    // emit(AuthLoading());

    await Future.delayed(const Duration(milliseconds: 500));

    final token = _prefs.getString('auth_token');
    final email = _prefs.getString('user_email');
    final username = _prefs.getString('user_username');

    print('   📦 Токен: ${token != null ? "✅ есть" : "❌ нет"}');
    print('   📦 Email: $email');
    print('   📦 Username: $username');

    if (token != null && email != null && username != null) {
      print('   ✅ Авторизация найдена, переходим на HomeScreen');
      emit(AuthSuccess(user: UserModel(
        id: _prefs.getInt('user_id') ?? 1,
        email: email,
        username: username,
        token: token,
        createdAt: DateTime.now(),
      )));
    } else {
      print('   ❌ Нет авторизации, показываем LoginScreen');
      emit(AuthInitial());
    }
  }
}