import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:versevo_app/core/theme.dart';
import 'package:versevo_app/presentation/bloc/auth/auth_bloc.dart';
import 'package:versevo_app/presentation/screens/home/home_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final prefs = await SharedPreferences.getInstance();

  // Для теста - пока закомментируем очистку
  // await prefs.clear();

  print('🚀 Запуск приложения...');
  print('   auth_token: ${prefs.getString('auth_token')}');
  print('   user_email: ${prefs.getString('user_email')}');

  runApp(MyApp(prefs: prefs));
}

class MyApp extends StatelessWidget {
  final SharedPreferences prefs;

  const MyApp({super.key, required this.prefs});

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (context) => AuthBloc(prefs)..add(AuthCheckStatusEvent()),
      child: MaterialApp(
        title: 'VERSEVO',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.lightTheme,
        home: const HomeScreen(), // Прямой переход на HomeScreen
      ),
    );
  }
}