import 'dart:io';
import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:versevo_app/core/theme.dart';
import 'package:versevo_app/data/api/document_api.dart';

class DocumentUploadScreen extends StatefulWidget {
  const DocumentUploadScreen({super.key});

  @override
  State<DocumentUploadScreen> createState() => _DocumentUploadScreenState();
}

class _DocumentUploadScreenState extends State<DocumentUploadScreen> {
  final DocumentApi _documentApi = DocumentApi();
  final List<PlatformFile> _selectedFiles = [];
  bool _isUploading = false;
  double _uploadProgress = 0.0;
  String? _errorMessage;
  String? _successMessage;
  String? _uploadStatus;
  final Map<String, String> _uploadedDocuments = {};

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Загрузка документов'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () {
            Navigator.pop(context, _uploadedDocuments.isNotEmpty ? true : null);
          },
        ),
      ),
      body: LayoutBuilder(
        builder: (context, constraints) {
          return SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 40),
            child: ConstrainedBox(
              constraints: BoxConstraints(minHeight: constraints.maxHeight - 40),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildInfoBanner(),

                  if (_errorMessage != null) _buildMessageBanner(_errorMessage!, isError: true),
                  if (_successMessage != null) _buildMessageBanner(_successMessage!, isError: false),
                  if (_uploadedDocuments.isNotEmpty) _buildUploadedSection(),

                  const SizedBox(height: 24),

                  _buildDropZone(constraints),

                  if (_isUploading) ...[
                    const SizedBox(height: 24),
                    _buildUploadProgress(),
                  ],

                  if (_selectedFiles.isNotEmpty && !_isUploading) ...[
                    const SizedBox(height: 24),
                    _buildSelectedFilesSection(),
                    const SizedBox(height: 20),
                    _buildUploadButton(),
                  ],

                  if (_selectedFiles.isEmpty && !_isUploading && _uploadedDocuments.isEmpty)
                    SizedBox(height: constraints.maxHeight * 0.3),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildInfoBanner() {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            AppTheme.primary.withValues(alpha: 0.08),
            AppTheme.accent.withValues(alpha: 0.04),
          ],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppTheme.primary.withValues(alpha: 0.12)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: AppTheme.primary.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(Icons.auto_awesome, color: AppTheme.primary, size: 18),
              ),
              const SizedBox(width: 10),
              Text(
                'Что происходит после загрузки',
                style: Theme.of(context).textTheme.titleLarge?.copyWith(color: AppTheme.primary),
              ),
            ],
          ),
          const SizedBox(height: 14),
          _buildInfoItem(Icons.language, 'Автоматическое определение языка', 'Английский, Русский и др.'),
          _buildInfoItem(Icons.auto_stories, 'Разбиение на главы', 'Автоматическое определение структуры'),
          _buildInfoItem(Icons.library_books, 'Добавление в библиотеку', 'Сразу доступен для чтения'),
          _buildInfoItem(Icons.translate, 'Автоматический перевод', 'Если документ на иностранном языке'),
          _buildInfoItem(Icons.psychology, 'AI-анализ', 'Персонажи, темы, тональность'),
        ],
      ),
    );
  }

  Widget _buildInfoItem(IconData icon, String title, String subtitle) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Container(
            width: 28,
            height: 28,
            decoration: BoxDecoration(
              color: AppTheme.success.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Icon(Icons.check, color: AppTheme.success, size: 16),
          ),
          const SizedBox(width: 10),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.titleSmall),
              Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildMessageBanner(String message, {required bool isError}) {
    final color = isError ? AppTheme.error : AppTheme.success;
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Row(
        children: [
          Icon(isError ? Icons.error_outline : Icons.check_circle_rounded, color: color, size: 22),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              message,
              style: TextStyle(color: color, fontWeight: FontWeight.w500, fontSize: 13),
            ),
          ),
          GestureDetector(
            onTap: () => setState(() => isError ? _errorMessage = null : _successMessage = null),
            child: Icon(Icons.close, color: color.withValues(alpha: 0.6), size: 18),
          ),
        ],
      ),
    );
  }

  Widget _buildDropZone(BoxConstraints constraints) {
    if (_isUploading) return const SizedBox.shrink();

    return GestureDetector(
      onTap: _isUploading ? null : _pickFiles,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(vertical: 48, horizontal: 24),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: AppTheme.primary.withValues(alpha: 0.2),
            width: 2,
            strokeAlign: BorderSide.strokeAlignInside,
          ),
          color: AppTheme.primary.withValues(alpha: 0.03),
        ),
        child: Column(
          children: [
            Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [
                    AppTheme.primary.withValues(alpha: 0.12),
                    AppTheme.accent.withValues(alpha: 0.08),
                  ],
                ),
                shape: BoxShape.circle,
              ),
              child: Icon(Icons.cloud_upload_outlined, size: 40, color: AppTheme.primary),
            ),
            const SizedBox(height: 20),
            Text(
              'Выберите файлы для загрузки',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            Text(
              'PDF, DOC, DOCX, TXT, EPUB — до 50 MB',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: AppTheme.textTertiary),
            ),
            const SizedBox(height: 24),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              decoration: BoxDecoration(
                color: AppTheme.primary,
                borderRadius: BorderRadius.circular(12),
                boxShadow: [
                  BoxShadow(
                    color: AppTheme.primary.withValues(alpha: 0.3),
                    blurRadius: 12,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.add_circle_outline, color: Colors.white, size: 20),
                  const SizedBox(width: 8),
                  Text(
                    'Выбрать файлы',
                    style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 15),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildUploadProgress() {
    final colorScheme = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: colorScheme.shadow.withValues(alpha: 0.06),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        children: [
          Row(
            children: [
              SizedBox(
                width: 24,
                height: 24,
                child: CircularProgressIndicator(
                  strokeWidth: 2.5,
                  value: _uploadProgress,
                  color: AppTheme.primary,
                  backgroundColor: AppTheme.borderLight,
                ),
              ),
              const SizedBox(width: 12),
              Text(
                'Загрузка файлов',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const Spacer(),
              Text(
                '${(_uploadProgress * 100).toStringAsFixed(0)}%',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(color: AppTheme.primary),
              ),
            ],
          ),
          const SizedBox(height: 16),
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: LinearProgressIndicator(
              value: _uploadProgress,
              minHeight: 6,
              backgroundColor: AppTheme.borderLight,
              color: AppTheme.primary,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            _uploadStatus ?? 'Обработка документа...',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(color: AppTheme.textSecondary),
          ),
        ],
      ),
    );
  }

  Widget _buildSelectedFilesSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(Icons.insert_drive_file, size: 18, color: AppTheme.textSecondary),
            const SizedBox(width: 6),
            Text(
              'Выбранные файлы (${_selectedFiles.length})',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ],
        ),
        const SizedBox(height: 12),
        ListView.separated(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: _selectedFiles.length,
          separatorBuilder: (_, __) => const SizedBox(height: 10),
          itemBuilder: (context, index) => _buildFileCard(_selectedFiles[index], index),
        ),
      ],
    );
  }

  Widget _buildUploadButton() {
    return SizedBox(
      width: double.infinity,
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(14),
          gradient: LinearGradient(
            colors: [AppTheme.primary, AppTheme.primaryDark],
          ),
          boxShadow: [
            BoxShadow(
              color: AppTheme.primary.withValues(alpha: 0.35),
              blurRadius: 16,
              offset: const Offset(0, 6),
            ),
          ],
        ),
        child: ElevatedButton.icon(
          onPressed: _uploadFiles,
          icon: const Icon(Icons.send_rounded, size: 20),
          label: const Text('Загрузить и обработать'),
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.transparent,
            shadowColor: Colors.transparent,
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 18),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
            textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
          ),
        ),
      ),
    );
  }

  Widget _buildUploadedSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(Icons.check_circle_rounded, size: 18, color: AppTheme.success),
            const SizedBox(width: 6),
            Text(
              'Загруженные документы (${_uploadedDocuments.length})',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(color: AppTheme.success),
            ),
          ],
        ),
        const SizedBox(height: 12),
        ..._uploadedDocuments.entries.map((entry) {
          return Container(
            margin: const EdgeInsets.only(bottom: 10),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            decoration: BoxDecoration(
              color: AppTheme.success.withValues(alpha: 0.06),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppTheme.success.withValues(alpha: 0.15)),
            ),
            child: Row(
              children: [
                Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: AppTheme.success.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(Icons.check_circle_rounded, color: AppTheme.success, size: 22),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(entry.key, overflow: TextOverflow.ellipsis, style: Theme.of(context).textTheme.titleSmall),
                      const SizedBox(height: 2),
                      Text(entry.value, style: Theme.of(context).textTheme.bodySmall),
                    ],
                  ),
                ),
              ],
            ),
          );
        }),
        const SizedBox(height: 20),
        SizedBox(
          width: double.infinity,
          child: ElevatedButton.icon(
            onPressed: () => Navigator.pop(context, true),
            icon: const Icon(Icons.library_books_rounded, size: 20),
            label: const Text('Перейти в библиотеку'),
          ),
        ),
      ],
    );
  }

  Widget _buildFileCard(PlatformFile file, int index) {
    final fileSizeMB = (file.size / 1024 / 1024).toStringAsFixed(2);
    final colorScheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        boxShadow: [
          BoxShadow(
            color: colorScheme.shadow.withValues(alpha: 0.06),
            blurRadius: 10,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Row(
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: _getFileColor(file.extension).withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(_getFileIcon(file.extension), color: _getFileColor(file.extension), size: 26),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  file.name,
                  style: Theme.of(context).textTheme.titleSmall,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 3),
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: _getFileColor(file.extension).withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        file.extension?.toUpperCase() ?? 'ФАЙЛ',
                        style: TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: _getFileColor(file.extension)),
                      ),
                    ),
                    const SizedBox(width: 6),
                    Flexible(child: Text('$fileSizeMB MB', style: Theme.of(context).textTheme.bodySmall, overflow: TextOverflow.ellipsis)),
                    const SizedBox(width: 6),
                    Flexible(child: Text(_getFileTypeDescription(file.extension), style: Theme.of(context).textTheme.bodySmall, overflow: TextOverflow.ellipsis)),
                  ],
                ),
              ],
            ),
          ),
          GestureDetector(
            onTap: _isUploading ? null : () => _removeFile(index),
            child: Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(
                color: AppTheme.error.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(Icons.close_rounded, color: AppTheme.error, size: 18),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _pickFiles() async {
    try {
      final result = await FilePicker.platform.pickFiles(
        allowMultiple: true,
        type: FileType.custom,
        allowedExtensions: ['pdf', 'doc', 'docx', 'txt', 'epub'],
      );
      if (result != null) {
        setState(() {
          _selectedFiles.addAll(result.files);
          _errorMessage = null;
        });
      }
    } catch (e) {
      setState(() => _errorMessage = 'Не удалось выбрать файлы: $e');
    }
  }

  void _removeFile(int index) {
    setState(() => _selectedFiles.removeAt(index));
  }

  Future<File?> _safeFileFromPlatformFile(PlatformFile file) async {
    final filePath = file.path;
    if (filePath == null) return null;
    try {
      final dir = await getTemporaryDirectory();
      final safeDir = Directory('${dir.path}/versevo_uploads');
      if (!await safeDir.exists()) {
        await safeDir.create(recursive: true);
      }
      final safeFile = File('${safeDir.path}/${file.name}');
      if (await safeFile.exists()) {
        await safeFile.delete();
      }
      await File(filePath).copy(safeFile.path);
      return safeFile;
    } catch (e) {
      return File(filePath);
    }
  }

  Future<void> _uploadFiles({List<PlatformFile>? files}) async {
    final targetFiles = files ?? List.from(_selectedFiles);
    if (targetFiles.isEmpty) return;

    for (final file in targetFiles) {
      if (file.size > 50 * 1024 * 1024) {
        if (!mounted) return;
        setState(() => _errorMessage = 'Файл "${file.name}" слишком большой (максимум 50MB)');
        return;
      }
    }

    if (!mounted) return;
    setState(() {
      _isUploading = true;
      _uploadProgress = 0.0;
      _errorMessage = null;
      _successMessage = null;
    });

    int successCount = 0;
    int errorCount = 0;
    final remainingFiles = <PlatformFile>[];

    for (int i = 0; i < targetFiles.length; i++) {
      final file = targetFiles[i];

      try {
        if (!mounted) return;
        setState(() {
          _uploadProgress = (i + 0.3) / targetFiles.length;
          _uploadStatus = 'Загрузка файла: ${file.name}';
        });

        if (file.path == null) {
          throw Exception('Путь к файлу не найден');
        }
        final safeTempFile = await _safeFileFromPlatformFile(file);
        if (safeTempFile == null) {
          throw Exception('Не удалось прочитать файл');
        }
        final document = await _documentApi.uploadDocument(safeTempFile);
        successCount++;

        if (!mounted) return;
        setState(() {
          _uploadProgress = (i + 0.7) / targetFiles.length;
          _uploadStatus = 'Обработка документа...';
        });

        _uploadedDocuments[document.filename] =
            '${document.language.toUpperCase()} • ${document.wordCount} слов';

      } catch (e) {
        final errMsg = e.toString();
        if (errMsg.contains('Таймаут') || errMsg.contains('502')) {
          remainingFiles.add(file);
        }
        errorCount++;
        if (!mounted) return;
        setState(() {
          _errorMessage = 'Ошибка загрузки "${file.name}": ${e.toString().replaceAll("Exception: ", "")}';
        });
      }

      if (!mounted) return;
      setState(() => _uploadProgress = (i + 1) / targetFiles.length);

      if (i < targetFiles.length - 1) {
        await Future.delayed(const Duration(milliseconds: 500));
      }
    }

    if (remainingFiles.isNotEmpty && successCount == 0) {
      if (!mounted) return;
      setState(() {
        _isUploading = false;
      });
      final retry = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          title: const Text('Сервер запускается...'),
          content: const Text('Бесплатный сервер Railway засыпает без активности. Обычно просыпается за 10-15 сек. Попробовать ещё раз?'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Отмена'),
            ),
            ElevatedButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Повторить'),
            ),
          ],
        ),
      );
      if (retry == true && mounted) {
        _uploadFiles(files: remainingFiles);
        return;
      }
    }

    if (!mounted) return;
    setState(() {
      _isUploading = false;
      if (successCount > 0) _selectedFiles.clear();

      if (errorCount == 0) {
        _successMessage = 'Все документы ($successCount) успешно загружены и обработаны!';
      } else if (successCount > 0) {
        _successMessage = 'Загружено $successCount документов, ошибок: $errorCount';
      }
    });
  }

  Color _getFileColor(String? extension) {
    switch (extension?.toLowerCase()) {
      case 'pdf':
        return Colors.red;
      case 'doc':
      case 'docx':
        return Colors.blue;
      case 'txt':
        return Colors.green;
      case 'epub':
        return Colors.purple;
      default:
        return AppTheme.primary;
    }
  }

  IconData _getFileIcon(String? extension) {
    switch (extension?.toLowerCase()) {
      case 'pdf':
        return Icons.picture_as_pdf;
      case 'doc':
      case 'docx':
        return Icons.description;
      case 'txt':
        return Icons.text_fields;
      case 'epub':
        return Icons.menu_book;
      default:
        return Icons.insert_drive_file;
    }
  }

  String _getFileTypeDescription(String? extension) {
    switch (extension?.toLowerCase()) {
      case 'pdf':
        return 'PDF документ';
      case 'doc':
      case 'docx':
        return 'Документ Word';
      case 'txt':
        return 'Текстовый файл';
      case 'epub':
        return 'Электронная книга';
      default:
        return 'Другой формат';
    }
  }
}
