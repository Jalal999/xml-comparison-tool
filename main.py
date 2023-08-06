import pandas as pd
import numpy as np
from lxml import html as html_parser
from copy import deepcopy
import time
import jinja2
import pdfkit
import html
import json
import re
import os


class xmlComparison():
    # compare two xml files converted as df
    def __init__(self, original, updated, debug=0):
        # border:thick solid red;
        # border:thick solid green;
        self.original = original
        self.updated = updated
        self.debug = debug
        self.original_selector = f'id="entity_id" style="'
        original_df = pd.read_xml(original, xpath=".//root//*")
        updated_df = pd.read_xml(updated, xpath=".//root//*")
        self.ts = round(time.time() * 1000)
        self.source_df = self.clean(original_df)
        self.target_df = self.clean(updated_df)
        self.source_df_analysis = self.analyze_df(self.source_df)
        self.target_df_analysis = self.analyze_df(self.target_df)
        self.entities_source, self.entities_target = self.get_entites_list()
        self.edges_source, self.edges_target = self.get_edges_list()
        self.compare_source_vertices_results = self.compare_source_vertices()
        self.compare_source_edges_results = self.compare_source_edges()
        self.compare_target_vertices_results = self.compare_target_vertices()
        self.compare_target_edges_results = self.compare_target_edges()
        self.all_vertices_analysis, self.all_edges_analysis = self.merge_results()
        with open(original) as my_file:
            self.original_xml = my_file.read()
        with open(updated) as my_file:
            self.updated_xml = my_file.read()
        self.final_xml = self.original_xml

    def clean(self, df):
        df_clean = df.dropna(axis=0, subset=["id"])
        df_clean = df.dropna(axis=1, how='all')
        return df_clean

    def get_vertex_id(self, analysis, vertex_title):
        vertices_list = analysis['vertices_list']
        for vertex in vertices_list:
            if vertex['title'] == vertex_title:
                return vertex['id']
        return None

    def get_edge_id(self, analysis, edge_source, edge_target):
        edge_source_id = self.get_vertex_id(analysis, edge_source)
        edge_target_id = self.get_vertex_id(analysis, edge_target)
        edges_list = analysis['edges_list']
        for edge in edges_list:
            if edge['source'] == edge_source_id and edge['target'] == edge_target_id:
                return edge['id']
        return None

    def check_identical(self):
        return self.source_df.equals(self.target_df)

    def convert_vertex_to_dict(self, row):
        content = row.value
        id = row.id
        response = html_parser.fromstring(content)
        dict = {'id': id}
        try:
            dict['title'] = response.xpath('//p/b/text()')[0]
            dict['attributes'] = response.xpath(
                '//p[./following-sibling::hr][./preceding-sibling::hr]/text()')
            dict['methods'] = response.xpath(
                '//hr[2]/following-sibling::p/text()')
        except IndexError:
            dict['title'] = content
        return dict

    def convert_edges_to_dict(self, row):
        dict = {'id': row.id}
        dict['source'] = row.source
        dict['target'] = row.target
        return dict

    def analyze_df(self, df):
        df_analysis_dict = {}
        df_analysis_dict['vertex_count'] = df[df.vertex ==
                                              1.0].vertex.shape[0]
        df_analysis_dict['edge_count'] = df[df.edge ==
                                            1.0].edge.shape[0]
        vertices = df[df.vertex == 1.0]
        edges = df[df.edge == 1.0]
        df_analysis_dict['vertices_list'] = vertices.apply(
            self.convert_vertex_to_dict, 1).tolist()
        df_analysis_dict['edges_list'] = edges.apply(
            self.convert_edges_to_dict, 1).tolist()
        return df_analysis_dict

    def get_entites_list(self):
        entities_source = {}
        source_vertices_list = self.source_df_analysis['vertices_list']
        for vertex in source_vertices_list:
            if vertex['title'] != "abstract class":
                entities_source[vertex["id"]] = vertex['title']
        entities_target = {}
        target_vertices_list = self.target_df_analysis['vertices_list']
        for vertex in target_vertices_list:
            if vertex['title'] != "abstract class":
                entities_target[vertex["id"]] = vertex['title']
        return entities_source, entities_target

    def get_edges_list(self):
        target_df_analysis = []
        for x in self.target_df_analysis['edges_list']:
            try:
                edge_dict = {}
                edge_dict['source'] = self.entities_target[x['source']]
                edge_dict['target'] = self.entities_target[x['target']]
                target_df_analysis.append(edge_dict)
            except KeyError:
                print(
                    "There is an edge that's not connected to any Class, make sure to extend it and connect it to a Class first")
        source_df_analysis = []
        for x in self.source_df_analysis['edges_list']:
            edge_dict = {}
            edge_dict['source'] = self.entities_source[x['source']]
            edge_dict['target'] = self.entities_source[x['target']]
            source_df_analysis.append(edge_dict)
        return source_df_analysis, target_df_analysis

    def get_different_content_details(self, source_content, target_content):
        removed_content = [
            x for x in source_content if x not in target_content]
        added_content = [x for x in target_content if x not in source_content]
        results = {}
        results["removed"] = removed_content
        results["removed_ids"] = [source_content.index(
            x) for x in source_content if x not in target_content]
        results["added"] = added_content
        results["added_ids"] = [target_content.index(
            x) for x in target_content if x not in source_content]
        return results

    def compare_source_vertices(self):
        results_list = []
        target_df_analysis = pd.DataFrame(
            self.target_df_analysis['vertices_list'])
        for vertex in [x for x in self.source_df_analysis['vertices_list'] if 'attributes' in x]:
            vertex_result_dict = {}
            vertex_result_dict['vertex_title'] = vertex['title']
            vertex_result_dict['id'] = vertex['id']
            if vertex['title'] in target_df_analysis.title.values:
                # vertex title exists
                target_attributes = target_df_analysis[target_df_analysis.title ==
                                                       vertex['title']].attributes.iloc[0]
                if vertex['attributes'] == target_attributes:
                    vertex_result_dict['attributes_status'] = 'Matched'
                else:
                    vertex_result_dict["attributes_status"] = "Not Matched"
                    vertex_result_dict["attributes_updates"] = self.get_different_content_details(
                        vertex['attributes'], target_attributes)
                target_methods = target_df_analysis[target_df_analysis.title ==
                                                    vertex['title']].methods.iloc[0]
                if vertex['methods'] == target_methods:
                    vertex_result_dict['methods_status'] = 'Matched'
                else:
                    vertex_result_dict["methods_status"] = "Not Matched"
                    vertex_result_dict["methods_updates"] = self.get_different_content_details(
                        vertex['methods'], target_methods)
                if vertex_result_dict['methods_status'] == 'Matched' and vertex_result_dict['attributes_status'] == 'Matched':
                    vertex_result_dict['status'] = 'Vertex Matched'
                else:
                    vertex_result_dict['status'] = 'Vertex Found but Not Matched'
            else:
                vertex_result_dict['status'] = 'Not Found'
            results_list.append(vertex_result_dict)
        return results_list

    def compare_source_edges(self):
        results_list = []
        for source_edge in deepcopy(self.edges_source):
            if source_edge in self.edges_target:
                source_edge['status'] = 'Matched'
            else:
                source_edge['status'] = 'Not Found'
            source_edge['id'] = self.get_edge_id(
                self.source_df_analysis, source_edge['source'], source_edge['target'])
            results_list.append(source_edge)
        return results_list
 
    def compare_target_vertices(self):
        results_list = []
        source_df_analysis = pd.DataFrame(
            self.source_df_analysis['vertices_list'])
        for vertex in [x for x in self.target_df_analysis['vertices_list'] if 'attributes' in x]:
            vertex_result_dict = {}
            vertex_result_dict['vertex_title'] = vertex['title']
            vertex_result_dict['id'] = vertex['id']
            if vertex['title'] not in source_df_analysis.title.values:
                # vertex title does not exists
                vertex_result_dict['status'] = 'New Vertex Added'
                results_list.append(vertex_result_dict)
        return results_list

    def compare_target_edges(self):
        results_list = []
        for target_edge in deepcopy(self.edges_target):
            if target_edge not in self.edges_source:
                target_edge['status'] = 'New Edge Added'
                target_edge['id'] = self.get_edge_id(
                    self.target_df_analysis, target_edge['source'], target_edge['target'])
                results_list.append(target_edge)
        return results_list

    def merge_results(self):
        all_vertices_analysis = []
        all_vertices_analysis.extend(self.compare_source_vertices())
        all_vertices_analysis.extend(self.compare_target_vertices())
        all_edges_analysis = []
        all_edges_analysis.extend(self.compare_source_edges())
        all_edges_analysis.extend(self.compare_target_edges())
        df = pd.DataFrame(all_vertices_analysis)
        df1 = df.pop('id')
        df['id'] = df1
        column_to_move = df.pop("status")
        # insert column with insert(location, column_name, column_value)
        df.insert(1, "status", column_to_move)
        vertices_analysis_file = f'vertices_analysis_{self.ts}.csv'
        if self.debug:
            df.to_csv(vertices_analysis_file, index=False)
            print(
                f'you can check the comparison results for the classes/entites as a table at this file {vertices_analysis_file}')
        self.vertices_analysis_table = df.to_html()

        edges_analysis_file = f'edges_analysis_{self.ts}.csv'
        df = pd.DataFrame(all_edges_analysis)
        if self.debug:
            df.to_csv(edges_analysis_file, index=False)
            print(
                f'you can check the comparison results for the edges as a table at this file {edges_analysis_file}')
        self.edges_analysis_table = df.to_html()

        return all_vertices_analysis, all_edges_analysis

    def print_report(self):
        # template_loader = jinja2.FileSystemLoader('./html_templates')
        # template_env = jinja2.Environment(loader=template_loader)
        xml = self.final_xml.replace(
            "border:solid red;border-color: var(--border-color);", "border:solid red;")
        xml = xml.replace(
            "border:solid green;border-color: var(--border-color);", "border:solid green;")
        xml = "\n".join(xml.split('\n')[1:])
        encodedHtml = html.escape(json.dumps(xml))
        context = {'xml_document': encodedHtml}
        context['Classes'] = self.vertices_analysis_table
        context['Edges'] = self.edges_analysis_table
        cwd = os.getcwd()
        context['original_path'] = cwd + '/' + self.original
        context['updated_path'] = cwd + '/' + self.updated
        context['original'] = self.original.split('/')[-1]
        context['updated'] = self.updated.split('/')[-1]
        html_template = 'report_template.html'
        template_loader = jinja2.FileSystemLoader('.')
        template_env = jinja2.Environment(loader=template_loader)
        template = template_env.get_template(html_template)
        output_text = template.render(
            context).replace("&quot;&quot;", "&quot;")
        f = open(
            f"Report_{self.original.split('/')[-1]}_{self.updated.split('/')[-1]}_{self.ts}.html", "w")
        f.write(output_text)
        f.close()
        print("the report was exported to this file",
              f"Report_{self.original.split('/')[-1]}_{self.updated.split('/')[-1]}_{self.ts}.html")

    def update_not_found_edge(self, edge):
        edge_id = edge['id']
        original_selector = self.original_selector.replace(
            "entity_id", edge_id)
        updated_text = original_selector + "strokeColor=red;"
        self.final_xml = self.final_xml.replace(
            original_selector, updated_text)
        return self.final_xml

    def update_not_found_vertex(self, vertex):
        vertex_selector = r'entity_id" value="(.*)" style="(.*)"'
        updated_selector = r'entity_id" value="\g<1>" style="strokeColor=red;\g<2>"'
        vertex_id = vertex['id']
        original_selector = vertex_selector.replace(
            "entity_id", vertex_id)
        updated_selector = updated_selector.replace(
            "entity_id", vertex_id)
        self.final_xml = re.sub(
            original_selector, updated_selector, self.final_xml)

        return self.final_xml

    def update_changed_vertix(self, vertex):
        vertex_id = vertex["id"]
        if vertex['attributes_status'] == 'Not Matched':
            self.update_changed_attributes(
                vertex, vertex["attributes_updates"], 'attributes')
        if vertex['methods_status'] == 'Not Matched':
            self.update_changed_attributes(
                vertex, vertex["methods_updates"], 'methods')

    def get_vertex_height(self, vertex_id):
        get_current_value_regex_template = r'mxCell id="vertex_id"[^<]*<mxGeometry[^<]*height="(\d+)'
        get_current_value_regex = get_current_value_regex_template.replace(
            'vertex_id', vertex_id)
        curent_height_value = re.findall(
            get_current_value_regex, self.final_xml)[0]
        return int(curent_height_value)

    def update_vertex_height(self, new_height, vertex_id):
        get_current_value_regex_template = r'(mxCell id="vertex_id"[^<]*<mxGeometry[^<]*height=")(\d+)'
        updated_regex_selector = r'\g<1>new_height'
        get_current_value_regex = get_current_value_regex_template.replace(
            'vertex_id', vertex_id)
        updated_regex_selector_value = updated_regex_selector.replace(
            'new_height', str(new_height))
        self.final_xml = re.sub(get_current_value_regex,
                                updated_regex_selector_value, self.final_xml)

    def update_vertex_x(self, new_x, vertex_id):
        get_current_value_regex_template = r'(mxCell id="vertex_id"[^<]*<mxGeometry[^<]*x=")(\d+)'
        updated_regex_selector = r'\g<1>new_x'
        get_current_value_regex = get_current_value_regex_template.replace(
            'vertex_id', vertex_id)
        updated_regex_selector_value = updated_regex_selector.replace(
            'new_x', str(new_x))
        self.final_xml = re.sub(get_current_value_regex,
                                updated_regex_selector_value, self.final_xml)

    def fix_missing_p_tags(self):
        select_mising_tags = r'&lt;br&gt;+ '
        replace_with_p = r'&lt;/p&gt;&lt;p style=&quot;margin:0px;margin-left:4px;&quot;&gt;+ '
        self.final_xml = self.final_xml.replace(
            select_mising_tags, replace_with_p)

    def update_changed_attributes(self, vertex, updates, updates_type):
        # removed attributes or methods
        vertex_id = vertex["id"]
        vertex_selector = r'id="entity_id"([^<]*)style=&quot;([^<]*)changed_attribute'
        added_attribute_template = '&lt;p style=&quot;border:solid green;margin:0px;margin-left:4px;&quot;&gt;new_attribute&lt;/p&gt;'
        added_attribute_selector = r'vertex_title&lt;/b&gt;&lt;/p&gt;&lt;hr size=&quot;1&quot;&gt;'
        added_method_selector = r'(vertex_title.*/p&gt;)'
        changed_selector = r'id="entity_id"\g<1>style=&quot;border:solid red;\g<2>changed_attribute'
        changed_attributes_list = updates['removed']
        for attribute in changed_attributes_list:
            original_selector = vertex_selector.replace(
                "entity_id", vertex_id).replace("changed_attribute", re.escape(attribute))
            updated_selector = changed_selector.replace(
                "entity_id", vertex_id).replace("changed_attribute", attribute)
            self.final_xml = re.sub(
                original_selector, updated_selector, self.final_xml)
            current_vertex_height = self.get_vertex_height(vertex_id)
            update_vertex_height = self.update_vertex_height(
                current_vertex_height+10, vertex_id)
        # new added attributes or methods
        added_attributes_list = updates['added']
        for attribute in added_attributes_list:
            new_added_selector = added_attribute_template.replace(
                'new_attribute', attribute)
            if updates_type == "attributes":
                added_vertex_title = added_attribute_selector.replace(
                    "vertex_title", vertex['vertex_title'])
                # &lt;p style=&quot;border:solid green;margin:0px;margin-left:4px;&quot;&gt;+ email: String&lt;/p&gt;

                self.final_xml = self.final_xml.replace(
                    added_vertex_title, added_vertex_title + new_added_selector)
            else:
                added_vertex_title = added_method_selector.replace(
                    "vertex_title", vertex['vertex_title'])
                self.final_xml = re.sub(
                    added_vertex_title, r'\g<1>' + new_added_selector, self.final_xml)
            current_vertex_height = self.get_vertex_height(vertex_id)
            update_vertex_height = self.update_vertex_height(
                current_vertex_height+25, vertex_id)

        return self.final_xml

    def update_new_edge(self, edge):
        edge_id = edge["id"].split('___')[0]
        duplicate_flag = edge["id"].split('___')[1] if len(
            edge["id"].split('___')) > 1 else None
        new_edge_selector = r'(<mxCell id="edge_id".*</mxCell>)'
        updated_xml = self.updated_xml.replace(
            '\n', ' ').replace('</mxCell>', '</mxCell>\n')
        new_edge_line = re.findall(
            new_edge_selector.replace("edge_id", edge_id), updated_xml)
        if new_edge_line:
            new_edge_line = new_edge_line[0]
            new_edge_line = new_edge_line.replace(
                'style="', 'style="strokeColor=green;')
            if duplicate_flag:
                new_edge_line = new_edge_line.replace(
                    f'id="{edge_id}"', f'id="{edge_id}_{duplicate_flag}"')
            self.final_xml = self.final_xml.replace(
                "</mxCell>", f"</mxCell>\n{new_edge_line}", 1)

    def get_vertex_coordinates(self, vertex_id, source):
        if source:
            df = self.source_df
        else:
            df = self.target_df
        vertex_index = df[df['id'] == vertex_id].index[0]
        vertex_point = (df.iloc[vertex_index+1]['x'],
                        df.iloc[vertex_index+1]['y'])
        vertex_width = df.iloc[vertex_index+1]['width']
        vertex_height = df.iloc[vertex_index+1]['height']
        return vertex_point, vertex_width, vertex_height

    def check_nearest_vertex(self, vertex_point):
        df = self.source_df
        df = df.fillna(0)
        points_list = df[(df['x'] > 0) & (df['height'] > 0)
                         ][['x', 'y']].values.tolist()
        points_array = np.array(points_list)
        vertex_point_array = np.array(vertex_point)
        distances = np.linalg.norm(points_array-vertex_point_array, axis=1)
        min_index = np.argmin(distances)
        closest_point = points_list[min_index]
        closest_point_width = df[(df['x'] == closest_point[0]) & (
            df['y'] == closest_point[1])]['width'].values[0]
        if vertex_point[0] < closest_point[0] + closest_point_width:
            return closest_point[0] + closest_point_width + 25
        else:
            return False

    def update_new_vertix(self, vertix):
        vertix_id = vertix["id"].split('___')[0]
        vertex_point, vertex_width, vertex_height = self.get_vertex_coordinates(
            vertix_id, False)
        check_nearest_vertex = self.check_nearest_vertex(
            vertex_point)
        duplicate_flag = vertix["id"].split('___')[1] if len(
            vertix["id"].split('___')) > 1 else None
        new_vertix_selector = r'(<mxCell id="vertix_id".*</mxCell>)'
        updated_xml = self.updated_xml.replace(
            '\n', ' ').replace('</mxCell>', '</mxCell>\n')
        new_vertix_line = re.findall(
            new_vertix_selector.replace("vertix_id", vertix_id), updated_xml)
        if new_vertix_line:
            new_vertix_line = new_vertix_line[0]
            new_vertix_line = new_vertix_line.replace(
                'style="', 'style="strokeColor=green;')
            if duplicate_flag:
                new_vertix_line = new_vertix_line.replace(
                    f'id="{vertix_id}"', f'id="{vertix_id}_{duplicate_flag}"')
            self.final_xml = self.final_xml.replace(
                "</mxCell>", f"</mxCell>\n{new_vertix_line}", 1)
        if check_nearest_vertex:
            self.update_vertex_x(check_nearest_vertex, vertix_id)

    def update_source_edges(self):
        for edge in self.all_edges_analysis:
            if edge['status'] == 'Not Found':
                self.update_not_found_edge(edge)
            elif edge["status"] == "New Edge Added":
                self.update_new_edge(edge)

    def check_duplicates_id(self):
        ids_set = set()
        for vertix in self.all_vertices_analysis:
            if vertix['id'] not in ids_set:
                ids_set.add(vertix['id'])
            else:
                vertix['id'] = vertix['id'] + '___1'
        ids_set = set()
        for edge in self.all_edges_analysis:
            if edge['id'] not in ids_set:
                ids_set.add(edge['id'])
            else:
                edge['id'] = edge['id'] + '___1'

    def update_source_vertices(self):
        for vertix in self.all_vertices_analysis:
            if vertix['status'] == 'Not Found':
                self.update_not_found_vertex(vertix)
            elif vertix["status"] == "Vertex Found but Not Matched":
                self.update_changed_vertix(vertix)
            elif vertix["status"] == "New Vertex Added":
                self.update_new_vertix(vertix)


if __name__ == '__main__':
    original_file = input("Enter the original file name:\n")
    updated_file = input("Enter the updated file name:\n")
    compare = xmlComparison(original_file, updated_file)
    compare.fix_missing_p_tags()
    compare.check_duplicates_id()
    compare.update_source_edges()
    compare.update_source_vertices()
    compare.print_report()
