import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:versevo_app/core/theme.dart';
import 'package:versevo_app/data/api/document_api.dart';
import 'package:versevo_app/data/api/translation_api.dart';
import 'package:versevo_app/data/models/document_model.dart';
import 'package:versevo_app/presentation/screens/documents/document_reader_screen.dart';
import 'package:versevo_app/presentation/screens/documents/analysis_screen.dart';
import 'package:versevo_app/presentation/screens/documents/ai_chat_screen.dart';
import 'package:versevo_app/presentation/screens/documents/document_upload_screen.dart';

class LibraryScreen extends StatefulWidget {
  const LibraryScreen({super.key});

  @override
  State<LibraryScreen> createState() => _LibraryScreenState();
}

class _LibraryScreenState extends State<LibraryScreen> {
  final DocumentApi _documentApi = DocumentApi();
  final TranslationApi _translationApi = TranslationApi();
  List<DocumentModel> _documents = [];
  final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();
  bool _isLoading = true;
  bool _isOpeningDocument = false;
  String? _errorMessage;
  String _searchQuery = '';
  final Map<int, bool> _isTranslating = {};

  @override
  void initState() {
    super.initState();
    _loadDocuments();
  }

  Future<void> _loadDocuments() async {
    if (mounted) {
      setState(() {
        _isLoading = true;
        _errorMessage = null;
      });
    }

    try {
      final documents = await _documentApi.getDocuments();
      if (mounted) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!mounted) return;
          setState(() {
            _documents = documents;
            _isLoading = false;
          });
        });
      }
    } catch (e) {
      if (mounted) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!mounted) return;
          setState(() {
            _errorMessage = e.toString();
            _isLoading = false;
          });
        });
      }
    }
  }

  String _extractErrorMessage(dynamic e) {
    if (e.toString().contains('502')) {
      return 'Сервер временно недоступен (502 Bad Gateway)\n\nПопробуйте позже или проверьте бэкенд на Railway.';
    }
    if (e.toString().contains('Failed host lookup')) {
      return 'Не удалось подключиться к серверу.\nПроверьте интернет-соединение.';
    }
    if (e.toString().contains('Connection timeout')) {
      return 'Таймаут соединения.\nСервер не отвечает.';
    }
    return 'Ошибка: ${e.toString().replaceAll("Exception: ", "")}';
  }

  Future<void> _deleteDocument(int documentId, int index) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text('Удалить документ?'),
        content: const Text('Документ будет удален безвозвратно.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Отмена'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Удалить', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      try {
        await _documentApi.deleteDocument(documentId);
        if (mounted) {
          setState(() => _documents.removeAt(index));
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: const Text('Документ удален'),
              backgroundColor: Colors.green,
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
          );
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Ошибка удаления: ${_extractErrorMessage(e)}'),
              backgroundColor: Colors.red,
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
          );
        }
      }
    }
  }

  List<DocumentModel> get _filteredDocuments {
    if (_searchQuery.isEmpty) return _documents;
    return _documents.where((doc) {
      final title = doc.title.toLowerCase();
      final filename = doc.filename.toLowerCase();
      final query = _searchQuery.toLowerCase();
      return title.contains(query) || filename.contains(query);
    }).toList();
  }

  Future<void> _openDocument(DocumentModel document) async {
    try {
      setState(() => _isOpeningDocument = true);

      DocumentModel documentToOpen = document;
      if (document.content == null || document.content!.isEmpty) {
        documentToOpen = await _documentApi.getDocument(document.id);
        final index = _documents.indexWhere((d) => d.id == document.id);
        if (index != -1) {
          setState(() => _documents[index] = documentToOpen);
        }
      }

      if (mounted) {
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (context) => DocumentReaderScreen(document: documentToOpen),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Не удалось открыть документ: ${_extractErrorMessage(e)}'),
            backgroundColor: Colors.red,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _isOpeningDocument = false);
    }
  }

  Future<void> _navigateToUploadScreen() async {
    final result = await Navigator.push<bool>(
      context,
      MaterialPageRoute(
        builder: (context) => const DocumentUploadScreen(),
      ),
    );
    if (result == true && mounted) {
      _loadDocuments();
    }
  }

  Future<void> _translateDocument(DocumentModel doc) async {
    try {
      setState(() => _isTranslating[doc.id] = true);

      String content = doc.content ?? '';
      if (content.isEmpty) {
        final fullDoc = await _documentApi.getDocument(doc.id);
        content = fullDoc.content ?? '';
      }
      if (content.isEmpty) throw Exception('Нет содержимого для перевода');

      if (content.length < 1000) {
        final translatedText = await _translationApi.translateText(
          text: content,
          targetLanguage: 'ru',
          sourceLanguage: doc.language,
        );
        _showTranslationResult(translatedText);
      } else {
        final previewContent = content.substring(0, min(1000, content.length));
        final translatedText = await _translationApi.translateText(
          text: previewContent,
          targetLanguage: 'ru',
          sourceLanguage: doc.language,
        );
        _showTranslationResult('$translatedText\n\n[Переведена только первая часть текста]');
      }

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Перевод выполнен успешно'),
          backgroundColor: Colors.green,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Ошибка перевода: ${_extractErrorMessage(e)}'),
          backgroundColor: Colors.red,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
      );
    } finally {
      if (mounted) setState(() => _isTranslating.remove(doc.id));
    }
  }

  void _showTranslationResult(String translatedText) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: Row(
          children: [
            Container(
              width: 32, height: 32,
              decoration: BoxDecoration(
                gradient: const LinearGradient(colors: [Color(0xFF6366F1), Color(0xFFEC4899)]),
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Icon(Icons.translate, color: Colors.white, size: 18),
            ),
            const SizedBox(width: 12),
            const Text('Перевод документа'),
          ],
        ),
        content: SingleChildScrollView(
          child: Text(translatedText, style: const TextStyle(fontSize: 14, height: 1.5)),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Закрыть'),
          ),
          TextButton(
            onPressed: () {
              Clipboard.setData(ClipboardData(text: translatedText));
              Navigator.pop(context);
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: const Text('Текст скопирован'),
                  behavior: SnackBarBehavior.floating,
                  duration: const Duration(seconds: 1),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
              );
            },
            child: const Text('Копировать'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Scaffold(
      key: _scaffoldKey,
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: Text('Моя библиотека', style: GoogleFonts.inter(fontWeight: FontWeight.w600)),
        centerTitle: false,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _isLoading ? null : _loadDocuments,
            tooltip: 'Обновить',
          ),
          IconButton(
            icon: const Icon(Icons.upload_file),
            onPressed: _navigateToUploadScreen,
            tooltip: 'Загрузить документ',
          ),
        ],
      ),
      floatingActionButton: null,
      body: Stack(
        children: [
          _isLoading
              ? const Center(child: CircularProgressIndicator())
              : _errorMessage != null
                  ? _buildErrorView(colorScheme)
                  : _documents.isEmpty
                      ? _buildEmptyView(colorScheme)
                      : _buildContent(colorScheme),
          Positioned(
            right: 16,
            bottom: 16,
            child: FloatingActionButton(
              onPressed: _navigateToUploadScreen,
              backgroundColor: colorScheme.primary,
              tooltip: 'Загрузить документ',
              child: const Icon(Icons.upload_file, color: Colors.white),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildErrorView(ColorScheme colorScheme) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 88, height: 88,
              decoration: BoxDecoration(
                color: colorScheme.error.withValues(alpha: 0.1),
                shape: BoxShape.circle,
              ),
              child: Icon(Icons.cloud_off, size: 44, color: colorScheme.error),
            ),
            const SizedBox(height: 20),
            Text(
              'Сервер недоступен',
              style: GoogleFonts.inter(fontSize: 20, fontWeight: FontWeight.bold, color: colorScheme.onSurface),
            ),
            const SizedBox(height: 8),
            Text(
              _errorMessage!,
              textAlign: TextAlign.center,
              style: TextStyle(color: colorScheme.onSurface.withValues(alpha: 0.6), height: 1.4),
            ),
            const SizedBox(height: 24),
            ElevatedButton.icon(
              onPressed: _loadDocuments,
              icon: const Icon(Icons.refresh, size: 18),
              label: const Text('Повторить'),
              style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEmptyView(ColorScheme colorScheme) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 100, height: 100,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  AppTheme.primary.withValues(alpha: 0.12),
                  AppTheme.secondary.withValues(alpha: 0.06),
                ],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              shape: BoxShape.circle,
            ),
            child: Icon(Icons.library_books, size: 48, color: AppTheme.primary),
          ),
          const SizedBox(height: 20),
          Text(
            'Библиотека пуста',
            style: GoogleFonts.inter(fontSize: 22, fontWeight: FontWeight.bold, color: colorScheme.onSurface),
          ),
          const SizedBox(height: 8),
          Text(
            'Загрузите первый документ',
            style: TextStyle(color: colorScheme.onSurface.withValues(alpha: 0.5), fontSize: 15),
          ),
          const SizedBox(height: 28),
          ElevatedButton.icon(
            onPressed: _navigateToUploadScreen,
            icon: const Icon(Icons.upload_file, size: 18),
            label: const Text('Загрузить документ'),
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 14),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildContent(ColorScheme colorScheme) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
          child: TextField(
            decoration: InputDecoration(
              hintText: 'Поиск документов...',
              hintStyle: TextStyle(color: colorScheme.onSurface.withValues(alpha: 0.35)),
              prefixIcon: Icon(Icons.search, color: colorScheme.onSurface.withValues(alpha: 0.35)),
              suffixIcon: _searchQuery.isNotEmpty
                  ? IconButton(
                      icon: Icon(Icons.clear, color: colorScheme.onSurface.withValues(alpha: 0.4), size: 20),
                      onPressed: () => setState(() => _searchQuery = ''),
                    )
                  : null,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(14),
                borderSide: BorderSide.none,
              ),
              filled: true,
              fillColor: colorScheme.primaryContainer.withValues(alpha: 0.3),
              contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
            ),
            style: TextStyle(color: colorScheme.onSurface),
            onChanged: (value) => setState(() => _searchQuery = value),
          ),
        ),

        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 4),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Документы (${_filteredDocuments.length})',
                style: GoogleFonts.inter(fontWeight: FontWeight.w600, fontSize: 15, color: colorScheme.onSurface),
              ),
              if (_searchQuery.isNotEmpty)
                GestureDetector(
                  onTap: () => setState(() => _searchQuery = ''),
                  child: Text(
                    'Очистить',
                    style: TextStyle(fontSize: 13, color: colorScheme.primary),
                  ),
                ),
            ],
          ),
        ),

        const SizedBox(height: 4),

        Expanded(
          child: RefreshIndicator(
            onRefresh: _loadDocuments,
            color: colorScheme.primary,
            child: Stack(
              children: [
                _filteredDocuments.isEmpty
                    ? ListView(
                        children: [
                          SizedBox(
                            height: MediaQuery.of(context).size.height * 0.25,
                            child: Center(
                              child: Column(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  Icon(Icons.search_off, size: 52, color: colorScheme.onSurface.withValues(alpha: 0.15)),
                                  const SizedBox(height: 12),
                                  Text(
                                    'Ничего не найдено',
                                    style: GoogleFonts.inter(fontSize: 16, color: colorScheme.onSurface.withValues(alpha: 0.4)),
                                  ),
                                  const SizedBox(height: 8),
                                  TextButton(
                                    onPressed: () => setState(() => _searchQuery = ''),
                                    child: const Text('Очистить поиск'),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ],
                      )
                    : ListView.builder(
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                        itemCount: _filteredDocuments.length,
                        itemBuilder: (context, index) {
                          final doc = _filteredDocuments[index];
                          return _buildDocumentCard(doc, index, colorScheme);
                        },
                      ),
                if (_isOpeningDocument)
                  Container(
                    color: colorScheme.shadow.withValues(alpha: 0.2),
                    child: const Center(child: CircularProgressIndicator()),
                  ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildDocumentCard(DocumentModel doc, int index, ColorScheme colorScheme) {
    final hasContent = doc.content != null && doc.content!.isNotEmpty;
    final isTranslating = _isTranslating[doc.id] == true;
    final fileIcon = _getFileIcon(doc.fileType);
    final fileColor = _getFileColor(doc.fileType);

    return Card(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 14),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: colorScheme.outline.withValues(alpha: 0.15)),
      ),
      child: InkWell(
        onTap: () => _openDocument(doc),
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 56, height: 56,
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [fileColor.withValues(alpha: 0.2), fileColor.withValues(alpha: 0.05)],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: fileColor.withValues(alpha: 0.25)),
                ),
                child: isTranslating
                    ? Center(
                        child: SizedBox(
                          width: 20, height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2, color: fileColor),
                        ),
                      )
                    : Icon(fileIcon, color: fileColor, size: 28),
              ),
              const SizedBox(width: 14),

              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            doc.title,
                            style: GoogleFonts.inter(
                              fontSize: 15, fontWeight: FontWeight.w600,
                              color: colorScheme.onSurface,
                            ),
                            overflow: TextOverflow.ellipsis,
                            maxLines: 2,
                          ),
                        ),
                        if (!hasContent)
                          Container(
                            margin: const EdgeInsets.only(left: 8),
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: Colors.orange.withValues(alpha: 0.12),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              'Нет контента',
                              style: TextStyle(fontSize: 10, color: Colors.orange[700], fontWeight: FontWeight.w500),
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 6,
                      runSpacing: 4,
                      children: [
                        _buildTag(doc.fileType.toUpperCase(), fileColor),
                        _buildTag('${doc.wordCount} слов', colorScheme.onSurface.withValues(alpha: 0.5)),
                        if (doc.language != 'ru' && doc.language.isNotEmpty)
                          _buildTag(doc.language.toUpperCase(), AppTheme.accent),
                        if (doc.chapterCount > 1)
                          _buildTag('${doc.chapterCount} гл.', AppTheme.secondary),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Icon(Icons.access_time, size: 12, color: colorScheme.onSurface.withValues(alpha: 0.35)),
                        const SizedBox(width: 4),
                        Text(
                          _formatDate(doc.createdAt),
                          style: TextStyle(fontSize: 12, color: colorScheme.onSurface.withValues(alpha: 0.4)),
                        ),
                      ],
                    ),
                  ],
                ),
              ),

              Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _buildActionIcon(Icons.translate, Colors.blue, isTranslating ? null : () => _translateDocument(doc), isTranslating),
                  const SizedBox(height: 4),
                  _buildActionIcon(Icons.analytics, AppTheme.primary, () async {
                    DocumentModel d = doc;
                    if (doc.content == null || doc.content!.isEmpty) {
                      try { d = await _documentApi.getDocument(doc.id); } catch (_) {}
                    }
                    if (context.mounted) {
                      Navigator.push(
                        context,
                        MaterialPageRoute(builder: (context) => AnalysisScreen(document: d)),
                      );
                    }
                  }, false),
                  const SizedBox(height: 4),
                  _buildActionIcon(Icons.auto_awesome, Colors.amber.shade600, () async {
                    DocumentModel d = doc;
                    if (doc.content == null || doc.content!.isEmpty) {
                      try { d = await _documentApi.getDocument(doc.id); } catch (_) {}
                    }
                    if (context.mounted) {
                      Navigator.push(
                        context,
                        MaterialPageRoute(builder: (context) => AiChatScreen(document: d)),
                      );
                    }
                  }, false),
                  const SizedBox(height: 4),
                  PopupMenuButton<String>(
                    icon: Icon(Icons.more_vert, size: 18, color: colorScheme.onSurface.withValues(alpha: 0.4)),
                    onSelected: (value) {
                      if (value == 'delete') _deleteDocument(doc.id, index);
                    },
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    itemBuilder: (context) => [
                      const PopupMenuItem(
                        value: 'delete',
                        child: Row(
                          children: [
                            Icon(Icons.delete, size: 18, color: Colors.red),
                            SizedBox(width: 8),
                            Text('Удалить', style: TextStyle(color: Colors.red)),
                          ],
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTag(String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        text,
        style: TextStyle(fontSize: 11, color: color, fontWeight: FontWeight.w500),
      ),
    );
  }

  Widget _buildActionIcon(IconData icon, Color color, VoidCallback? onPressed, bool isLoading) {
    final effectiveOpacity = onPressed == null ? 0.4 : 1.0;
    return Opacity(
      opacity: effectiveOpacity,
      child: Container(
        width: 32, height: 32,
        decoration: BoxDecoration(
          color: color.withValues(alpha: isLoading ? 0.15 : 0.08),
          borderRadius: BorderRadius.circular(8),
        ),
        child: isLoading
            ? Padding(
                padding: const EdgeInsets.all(7),
                child: CircularProgressIndicator(strokeWidth: 2, color: color),
              )
            : IconButton(
                icon: Icon(icon, size: 16, color: color),
                onPressed: onPressed,
                padding: EdgeInsets.zero,
              ),
      ),
    );
  }

  Color _getFileColor(String fileType) {
    switch (fileType.toLowerCase()) {
      case 'pdf': return Colors.red;
      case 'docx': case 'doc': return Colors.blue;
      case 'txt': return Colors.green;
      case 'epub': return Colors.purple;
      default: return Colors.grey;
    }
  }

  IconData _getFileIcon(String fileType) {
    switch (fileType.toLowerCase()) {
      case 'pdf': return Icons.picture_as_pdf;
      case 'docx': case 'doc': return Icons.description;
      case 'txt': return Icons.text_fields;
      case 'epub': return Icons.menu_book;
      default: return Icons.insert_drive_file;
    }
  }

  String _formatDate(DateTime date) {
    final now = DateTime.now();
    final difference = now.difference(date);
    if (difference.inDays == 0) return 'сегодня';
    if (difference.inDays == 1) return 'вчера';
    if (difference.inDays < 7) return '${difference.inDays} дн. назад';
    if (difference.inDays < 30) {
      final weeks = (difference.inDays / 7).floor();
      return '$weeks ${_pluralize(weeks, 'нед.', 'нед.', 'нед.')} назад';
    }
    return '${date.day.toString().padLeft(2, '0')}.${date.month.toString().padLeft(2, '0')}.${date.year}';
  }

  String _pluralize(int number, String one, String two, String many) {
    if (number % 10 == 1 && number % 100 != 11) return one;
    if (number % 10 >= 2 && number % 10 <= 4 && (number % 100 < 10 || number % 100 >= 20)) return two;
    return many;
  }
}
