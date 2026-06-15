  import 'dart:io';
  import 'package:image_picker/image_picker.dart';
  import 'package:path_provider/path_provider.dart';
  import 'package:path/path.dart' as p;
  import 'package:shared_preferences/shared_preferences.dart';

  class AvatarService {
    static final AvatarService _instance = AvatarService._internal();
    factory AvatarService() => _instance;
    AvatarService._internal();

    final ImagePicker _picker = ImagePicker();
    static const String _avatarKey = 'user_avatar_path';

    // Выбрать фото из галереи
    Future<File?> pickImageFromGallery() async {
      try {
        final XFile? pickedFile = await _picker.pickImage(
          source: ImageSource.gallery,
          maxWidth: 800,
          maxHeight: 800,
          imageQuality: 85,
        );

        if (pickedFile != null) {
          return File(pickedFile.path);
        }
        return null;
      } catch (e) {
        print('❌ Ошибка выбора фото: $e');
        return null;
      }
    }

    // Сделать фото с камеры
    Future<File?> takePhotoWithCamera() async {
      try {
        final XFile? pickedFile = await _picker.pickImage(
          source: ImageSource.camera,
          maxWidth: 800,
          maxHeight: 800,
          imageQuality: 85,
        );

        if (pickedFile != null) {
          return File(pickedFile.path);
        }
        return null;
      } catch (e) {
        print('❌ Ошибка камеры: $e');
        return null;
      }
    }

    // Сохранить аватарку в локальное хранилище
    Future<String> saveAvatar(File imageFile) async {
      try {
        // Получаем директорию для сохранения
        final appDir = await getApplicationDocumentsDirectory();
        final avatarDir = Directory('${appDir.path}/avatars');

        if (!await avatarDir.exists()) {
          await avatarDir.create(recursive: true);
        }

        // Создаем уникальное имя файла
        final timestamp = DateTime.now().millisecondsSinceEpoch;
        final extension = p.extension(imageFile.path);
        final fileName = 'avatar_$timestamp$extension';
        final savedPath = '${avatarDir.path}/$fileName';

        // Копируем файл
        await imageFile.copy(savedPath);

        // Сохраняем путь в SharedPreferences
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString(_avatarKey, savedPath);

        print('✅ Аватар сохранен: $savedPath');
        return savedPath;
      } catch (e) {
        print('❌ Ошибка сохранения аватарки: $e');
        rethrow;
      }
    }

    // Получить сохраненную аватарку
    Future<String?> getSavedAvatarPath() async {
      final prefs = await SharedPreferences.getInstance();
      final path = prefs.getString(_avatarKey);

      if (path != null) {
        final file = File(path);
        if (await file.exists()) {
          return path;
        } else {
          // Если файл не существует, удаляем путь
          await prefs.remove(_avatarKey);
        }
      }

      return null;
    }

    // Удалить аватарку
    Future<void> deleteAvatar() async {
      try {
        final path = await getSavedAvatarPath();
        if (path != null) {
          final file = File(path);
          if (await file.exists()) {
            await file.delete();
          }
        }

        final prefs = await SharedPreferences.getInstance();
        await prefs.remove(_avatarKey);

        print('🗑️ Аватар удален');
      } catch (e) {
        print('❌ Ошибка удаления аватарки: $e');
      }
    }

    // Проверить наличие аватарки
    Future<bool> hasAvatar() async {
      final path = await getSavedAvatarPath();
      return path != null;
    }
  }