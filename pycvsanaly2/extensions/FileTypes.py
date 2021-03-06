# Copyright (C) 2008 LibreSoft
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# Authors :
#       Carlos Garcia Campos <carlosgc@gsyc.escet.urjc.es>

from pycvsanaly2.Database import (SqliteDatabase, MysqlDatabase, 
    TableAlreadyExists, statement)
from pycvsanaly2.extensions import (Extension, register_extension, 
    ExtensionRunError)
from pycvsanaly2.extensions.file_types import guess_file_type
from pycvsanaly2.utils import to_utf8, uri_to_filename


class DBFileType(object):

    id_counter = 1

    __insert__ = """INSERT INTO file_types (id, file_id, type) 
                    values (?, ?, ?)"""

    def __init__(self, id, type, file_id):
        if id is None:
            self.id = DBFileType.id_counter
            DBFileType.id_counter += 1
        else:
            self.id = id

        self.type = to_utf8(type)
        self.file_id = file_id


class FileTypes(Extension):
    
    def __init__(self):
        self.db = None
    
    def __create_table(self, cnn):
        cursor = cnn.cursor()

        if isinstance(self.db, SqliteDatabase):
            import sqlite3.dbapi2
            
            try:
                cursor.execute("CREATE TABLE file_types (" +
                                "id integer primary key," +
                                "file_id integer," +
                                "type varchar" +
                                ")")
            except sqlite3.dbapi2.OperationalError:
                cursor.close()
                raise TableAlreadyExists
            except:
                raise
        elif isinstance(self.db, MysqlDatabase):
            import MySQLdb

            try:
                cursor.execute("CREATE TABLE file_types (" +
                                "id INT primary key," +
                                "file_id integer REFERENCES files(id)," +
                                "type mediumtext" +
                                ") CHARACTER SET=utf8")
            except MySQLdb.OperationalError, e:
                if e.args[0] == 1050:
                    cursor.close()
                    raise TableAlreadyExists
                raise
            except:
                raise
            
        cnn.commit()
        cursor.close()
        
    def __create_indices(self, cnn):
        cursor = cnn.cursor()
        if isinstance(self.db, MysqlDatabase):
            import MySQLdb
            
            try:
                cursor.execute("create index parent_id on file_links(parent_id)")
            except MySQLdb.OperationalError, e:
                if e.args[0] != 1061:
                    cursor.close()
                    raise
                
            try:
                cursor.execute("create index repository_id on files(repository_id)")
            except MySQLdb.OperationalError, e:
                if e.args[0] != 1061:
                    cursor.close()
                    raise
            
        cursor.close()


    def __get_files_for_repository(self, repo_id, cursor):
        query = "SELECT ft.file_id from file_types ft, files f " + \
                "WHERE f.id = ft.file_id and f.repository_id = ?"
        cursor.execute(statement(query, self.db.place_holder), (repo_id,))
        files = [res[0] for res in cursor.fetchall()]

        return files
        
    def run(self, repo, uri, db):
        self.db = db

        path = uri_to_filename(uri)
        if path is not None:
            repo_uri = repo.get_uri_for_path(path)
        else:
            repo_uri = uri
        
        cnn = self.db.connect()

        cursor = cnn.cursor()
        cursor.execute(statement("SELECT id from repositories where uri = ?", 
                                 db.place_holder), (repo_uri,))
        repo_id = cursor.fetchone()[0]
        
        files = []
        
        try:
            self.__create_table(cnn)
        except TableAlreadyExists:
            cursor.execute(statement("SELECT max(id) from file_types", 
                                     db.place_holder))
            id = cursor.fetchone()[0]
            if id is not None:
                DBFileType.id_counter = id + 1

            files = self.__get_files_for_repository(repo_id, cursor)
        except Exception, e:
            raise ExtensionRunError(str(e))
        
        self.__create_indices(cnn)
        
        query = """select distinct f.id fid, f.file_name fname
                from files f
                where f.repository_id = ?
                and not exists (select id from file_links where parent_id = f.id)"""

        cursor.execute(statement(query, db.place_holder), (repo_id,))
        write_cursor = cnn.cursor()
        rs = cursor.fetchmany()
        while rs:
            types = []

            for file_id, file_name in rs:
                if file_id in files:
                    continue
                
                type = guess_file_type(file_name)
                types.append(DBFileType(None, type, file_id))

            if types:
                file_types = [(type.id, type.file_id, type.type) \
                              for type in types]
                write_cursor.executemany(statement(DBFileType.__insert__, 
                                                   self.db.place_holder), 
                                                   file_types)

            rs = cursor.fetchmany()
            
        cnn.commit()
        write_cursor.close()
        cursor.close()
        cnn.close()
        
    def backout(self, repo, uri, db):
        update_statement = """delete from file_types where
                              file_id in (select id from files f
                                            where f.repository_id = ?)"""

        self._do_backout(repo, uri, db, update_statement)
        

register_extension("FileTypes", FileTypes)
