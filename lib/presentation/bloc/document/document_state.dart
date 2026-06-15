part of 'document_bloc.dart';

abstract class DocumentState extends Equatable {
  const DocumentState();

  @override
  List<Object> get props => [];
}

class DocumentInitial extends DocumentState {}

class DocumentLoading extends DocumentState {}

class DocumentLoaded extends DocumentState {
  final List<DocumentModel> documents;

  const DocumentLoaded({required this.documents});

  @override
  List<Object> get props => [documents];
}

class DocumentError extends DocumentState {
  final String error;

  const DocumentError({required this.error});

  @override
  List<Object> get props => [error];
}