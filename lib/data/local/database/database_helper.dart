import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart';

class DatabaseHelper {
  static final DatabaseHelper instance = DatabaseHelper._init();
  static Database? _database;

  DatabaseHelper._init();

  Future<Database> get database async {
    if (_database != null) return _database!;
    _database = await _initDB('versevo.db');
    return _database!;
  }

  Future<Database> _initDB(String filePath) async {
    final dbPath = await getDatabasesPath();
    final path = join(dbPath, filePath);

    return await openDatabase(
      path,
      version: 1,
      onCreate: _createDB,
    );
  }

  Future<void> _createDB(Database db, int version) async {
    print('🔄 Создание базы данных...');

    // Таблица пользователей
    await db.execute('''
      CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        username TEXT NOT NULL,
        hashed_password TEXT NOT NULL,
        created_at TEXT,
        last_login TEXT,
        avatar_path TEXT
      )
    ''');

    // Таблица документов
    await db.execute('''
      CREATE TABLE documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT,
        filename TEXT NOT NULL,
        content TEXT,
        translated_content TEXT,
        language TEXT DEFAULT 'ru',
        file_type TEXT DEFAULT 'txt',
        file_path TEXT,
        file_size INTEGER DEFAULT 0,
        word_count INTEGER DEFAULT 0,
        char_count INTEGER DEFAULT 0,
        chapter_count INTEGER DEFAULT 0,
        reading_time_minutes INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT
      )
    ''');

    // Таблица заметок
    await db.execute('''
      CREATE TABLE document_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        selected_text TEXT,
        chapter_index INTEGER DEFAULT 0,
        text_position INTEGER,
        color TEXT DEFAULT 'yellow',
        is_highlight BOOLEAN DEFAULT 1,
        created_at TEXT
      )
    ''');

    // Таблица прогресса чтения
    await db.execute('''
      CREATE TABLE reading_progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        chapter_index INTEGER DEFAULT 0,
        scroll_position REAL DEFAULT 0.0,
        timestamp TEXT
      )
    ''');

    // Таблица анализа
    await db.execute('''
      CREATE TABLE document_analysis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL,
        analysis_type TEXT DEFAULT 'full',
        summary TEXT,
        themes TEXT,
        sentiment TEXT,
        writing_style TEXT,
        key_points TEXT,
        entities TEXT,
        ai_analysis BOOLEAN DEFAULT 0,
        ai_provider TEXT,
        analysis_timestamp TEXT,
        created_at TEXT
      )
    ''');

    // Таблица избранных цитат
    await db.execute('''
      CREATE TABLE favorite_quotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        quote TEXT NOT NULL,
        start_position INTEGER,
        end_position INTEGER,
        note TEXT,
        document_title TEXT,
        document_language TEXT DEFAULT 'ru',
        created_at TEXT
      )
    ''');

    // Таблица кэша переводов
    await db.execute('''
      CREATE TABLE translation_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        original_text_hash TEXT UNIQUE NOT NULL,
        original_text TEXT NOT NULL,
        translated_text TEXT NOT NULL,
        source_language TEXT DEFAULT 'en',
        target_language TEXT DEFAULT 'ru',
        style TEXT DEFAULT 'artistic',
        translation_service TEXT DEFAULT 'gemini',
        created_at TEXT
      )
    ''');

    print('✅ База данных создана успешно');

    // Создаем демо пользователя
    await db.insert('users', {
      'email': 'demo@example.com',
      'username': 'Demo User',
      'hashed_password': 'demopassword123',
      'created_at': DateTime.now().toIso8601String(),
    });

    // Создаем демо документы
    await db.insert('documents', {
      'title': 'Гордость и предубеждение',
      'filename': 'pride_and_prejudice.txt',
      'content': 'Глава 1\n\nЭто общепризнанная истина, что холостой мужчина, обладающий хорошим состоянием, непременно нуждается в жене.',
      'language': 'ru',
      'file_type': 'txt',
      'word_count': 250,
      'char_count': 1500,
      'reading_time_minutes': 5,
      'created_at': DateTime.now().toIso8601String(),
      'updated_at': DateTime.now().toIso8601String(),
    });

    await db.insert('documents', {
      'title': 'Преступление и наказание',
      'filename': 'crime_and_punishment.txt',
      'content': 'В начале июля, в чрезвычайно жаркое время, под вечер, один молодой человек вышел из своей каморки...',
      'language': 'ru',
      'file_type': 'txt',
      'word_count': 300,
      'char_count': 1800,
      'reading_time_minutes': 7,
      'created_at': DateTime.now().toIso8601String(),
      'updated_at': DateTime.now().toIso8601String(),
    });

    print('Добавление демо-данных');
  }

  Future<void> close() async {
    final db = await instance.database;
    db.close();
  }
}