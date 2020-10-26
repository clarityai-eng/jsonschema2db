# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2020-10-26

This is the first release of the jsonschema2ddl repo. This project is a direct fork from the original.

In this first we don't include major changes in functionality but there is a good amount of code refactor that will make this project more maintainable.

### Added

- Don't drop the schema when creating the tables by default. A new parameter is introduced to do so.
- Provide options to select whether to drop the tables if exists and with cascade or not.
- Provide an option to autocommit the changes in the schema creation.

### Changed

- docs: Use different docs structure
- chore: Use poetry for dependency and publishing
- chore: Provide Makefile for development
- chore: More elaborate travis.ci to be able to push based on tags
- chore: Change the project structure for the company python standars
- tests: Use testscontainers to be able to tests the postgres inserts
- feat: code is organized in a more object oriented model structure for easy extensibility and mantainability.
